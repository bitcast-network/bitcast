"""Async client for the YouTube Data v3, Analytics v2 and transcript APIs.

Talks REST directly with the miner-supplied OAuth bearer token — no Google
client libraries needed on the validator.
"""

import asyncio
import hashlib
from datetime import UTC, date, datetime, timedelta

import bittensor as bt
import httpx

from bitcast.config import (
    TRANSCRIPT_MAX_RETRY,
    YT_ANALYTICS_QUERIES_PER_MINUTE,
    YT_LOOKBACK,
    YT_MAX_CONCURRENT_ANALYTICS,
    YT_MAX_VIDEOS,
    get_settings,
)
from bitcast.http import RETRYABLE_STATUSES, request_with_retry
from bitcast.validator.youtube.cache import SearchCache
from bitcast.validator.youtube.timestamps import parse_timestamp

DATA_API_URL = "https://www.googleapis.com/youtube/v3"
ANALYTICS_API_URL = "https://youtubeanalytics.googleapis.com/v2/reports"
TRANSCRIPT_API_URL = "https://youtube-transcriptor.p.rapidapi.com/transcript"
TRANSCRIPT_API_HOST = "youtube-transcriptor.p.rapidapi.com"

_REQUEST_TIMEOUT = 30.0
_VIDEO_BATCH_SIZE = 50

# --- Reporting-only analytics -------------------------------------------------
# None of the following feeds scoring. They restore the channel and per-video
# figures v1 published, which the creator portal and campaign dashboards read.

_CHANNEL_SCALAR_METRICS = ["comments", "likes", "shares", "subscribersLost"]
_CHANNEL_SCALAR_METRICS_YPP = ["monetizedPlaybacks"]
_CHANNEL_DAY_METRICS = ["subscribersGained"]
_CHANNEL_DAY_METRICS_YPP = ["estimatedAdRevenue"]

# (payload key, metric, dimension)
_CHANNEL_BREAKDOWNS = (
    ("trafficSourceViews", "views", "insightTrafficSourceType"),
    ("trafficSourceMinutes", "estimatedMinutesWatched", "insightTrafficSourceType"),
    ("countryViews", "views", "country"),
    ("countryMinutes", "estimatedMinutesWatched", "country"),
)

_VIDEO_DAY_METRICS = ["views", "videosAddedToPlaylists"]
_VIDEO_DAY_METRICS_YPP = ["estimatedAdRevenue", "cpm"]

# (payload key, metric, dimension) — reported per day as {day: {dimension: value}}
_VIDEO_DAY_BREAKDOWNS = (
    ("deviceTypeMinutes", "estimatedMinutesWatched", "deviceType"),
    ("operatingSystemMinutes", "estimatedMinutesWatched", "operatingSystem"),
    ("trafficSourceMinutes", "estimatedMinutesWatched", "insightTrafficSourceType"),
    ("avgViewPercentageByTrafficSource", "averageViewPercentage", "insightTrafficSourceType"),
)

# Reporting-only per-video analytics: the window matches v1 so the stored
# figures (and the CPM spend estimates derived from them) stay comparable.
_VIDEO_ANALYTICS_WINDOW = 365

# (payload key, metric, dimension) — each costs one extra Analytics call.
_VIDEO_ANALYTICS_BREAKDOWNS = (
    ("trafficSourceMinutes", "estimatedMinutesWatched", "insightTrafficSourceType"),
    ("countryMinutes", "estimatedMinutesWatched", "country"),
    ("creatorContentTypeMinutes", "estimatedMinutesWatched", "creatorContentType"),
    ("subscribedStatusMinutes", "averageViewPercentage", "subscribedStatus"),
    ("elapsedVideoTimeRatioAudienceWatchRatio", "audienceWatchRatio", "elapsedVideoTimeRatio"),
)


class _RateLimiter:
    """Paces requests to a sustained ceiling, shared across every client.

    Google meters the Analytics API per *project*, so the budget belongs to
    the process, not to any one OAuth user. Requests are handed evenly spaced
    slots: they still overlap where latency allows, but the sustained rate
    cannot spike into the per-minute limit however many run at once.

    The read-modify-write below has no await between read and write, so under
    asyncio it cannot interleave and needs no lock.
    """

    def __init__(self, per_minute: int) -> None:
        self._interval = 60.0 / per_minute if per_minute > 0 else 0.0
        self._next_slot = 0.0

    async def acquire(self) -> None:
        if self._interval <= 0:
            return
        loop = asyncio.get_running_loop()
        now = loop.time()
        slot = max(now, self._next_slot)
        self._next_slot = slot + self._interval
        delay = slot - now
        if delay > 0:
            await asyncio.sleep(delay)


_ANALYTICS_RATE_LIMITER = _RateLimiter(YT_ANALYTICS_QUERIES_PER_MINUTE)

_MAX_ATTEMPTS = 3
_RETRY_DELAY = 0.5


class YouTubeApiError(Exception):
    """A YouTube API call failed definitively (permissions, not found, bad request)."""


class YouTubeTransientError(YouTubeApiError):
    """A YouTube API call still failed with a retryable condition after retries.

    Raised for network errors and {429, 5xx} responses once attempts are
    exhausted. Callers must never read a definitive fact (e.g. "this channel is
    not in the YouTube Partner Program") out of one of these — the request
    simply never got an answer.
    """


def discrete_id(raw_id: str) -> str:
    """Stable pseudonymous id published instead of the raw channel/video id."""
    return "bitcast_" + hashlib.sha256(raw_id.encode()).hexdigest()[:8]


class YouTubeClient:
    """All YouTube API access for one account (one OAuth access token)."""

    def __init__(
        self,
        access_token: str,
        session: httpx.AsyncClient,
        search_cache: SearchCache | None = None,
    ) -> None:
        self._headers = {"Authorization": f"Bearer {access_token}"}
        self._session = session
        self._search_cache = search_cache
        self.data_api_calls = 0
        self.analytics_api_calls = 0
        # Google enforces "Queries per minute per user" on the Analytics API,
        # and one client is one OAuth user — so the ceiling belongs here,
        # covering every caller rather than each of them separately.
        self._analytics_gate = asyncio.Semaphore(YT_MAX_CONCURRENT_ANALYTICS)

    async def _get(self, url: str, params: dict) -> dict:
        """GET a YouTube endpoint, retrying only conditions that may resolve themselves.

        Raises:
            YouTubeTransientError: Network failure or {429, 5xx} after retries.
            YouTubeApiError: A definitive 4xx (permissions, not found, bad request),
                returned on the first attempt without retrying.
        """
        try:
            response = await request_with_retry(
                self._session,
                "GET",
                url,
                params=params,
                headers=self._headers,
                timeout=_REQUEST_TIMEOUT,
                attempts=_MAX_ATTEMPTS,
                retry_delay=_RETRY_DELAY,
                backoff="exponential",
                honor_retry_after=True,
                label="youtube",
            )
        except httpx.HTTPError as err:
            raise YouTubeTransientError(f"{url} failed: {err}") from err

        if response.status_code >= 400:
            message = f"{url} returned {response.status_code}: {response.text[:300]}"
            if response.status_code in RETRYABLE_STATUSES:
                raise YouTubeTransientError(message)
            raise YouTubeApiError(message)
        return response.json()

    # --- Channel --------------------------------------------------------------

    async def get_channel_data(self, discrete_mode: bool = True) -> dict:
        """Snippet + statistics for the token's own channel."""
        self.data_api_calls += 1
        data = await self._get(
            f"{DATA_API_URL}/channels",
            {"part": "snippet,contentDetails,statistics", "mine": "true"},
        )
        items = data.get("items") or []
        if not items:
            raise YouTubeApiError("Token has no associated channel")
        channel = items[0]
        channel_id = channel["id"]
        return {
            "id": channel_id if not discrete_mode else None,
            "bitcastChannelId": discrete_id(channel_id),
            "title": channel["snippet"].get("title", ""),
            "channel_start": channel["snippet"].get("publishedAt", ""),
            "viewCount": channel["statistics"].get("viewCount", "0"),
            "subCount": channel["statistics"].get("subscriberCount", "0"),
            "videoCount": channel["statistics"].get("videoCount", "0"),
            "uploads_playlist": channel["contentDetails"]["relatedPlaylists"].get("uploads"),
            "_raw_channel_id": channel_id,
        }

    async def _analytics_query(
        self,
        start: date,
        end: date,
        metrics: list[str],
        dimensions: str | None = None,
        filters: str | None = None,
    ) -> dict:
        """Run one Analytics API report and key the result rows by metric name.

        Without dimensions, returns ``{metric: scalar}``. With dimensions,
        returns ``{metric: {dimension_value: value}}``, keyed on the first
        dimension — ``{date_str: value}`` for ``day``, ``{country: value}``
        for ``country``, and so on.
        """
        self.analytics_api_calls += 1
        params = {
            "ids": "channel==MINE",
            "startDate": start.isoformat(),
            "endDate": end.isoformat(),
            "metrics": ",".join(metrics),
        }
        if dimensions:
            params["dimensions"] = dimensions
        if filters:
            params["filters"] = filters
        await _ANALYTICS_RATE_LIMITER.acquire()
        async with self._analytics_gate:
            data = await self._get(ANALYTICS_API_URL, params)

        headers = [column["name"] for column in data.get("columnHeaders", [])]
        rows = data.get("rows") or []
        if not dimensions:
            values = rows[0] if rows else [0] * len(metrics)
            return dict(zip(headers, values, strict=False))

        key_field = dimensions.split(",")[0]
        result: dict = {metric: {} for metric in metrics}
        for row in rows:
            entry = dict(zip(headers, row, strict=False))
            key = entry.get(key_field)
            for metric in metrics:
                if key is not None and metric in entry:
                    result[metric][key] = entry[metric]
        return result

    async def _analytics_rows(
        self,
        start: date,
        end: date,
        metrics: list[str],
        dimensions: str,
        filters: str | None = None,
    ) -> list[dict]:
        """Raw Analytics rows as dicts, for reports keyed on more than one dimension."""
        self.analytics_api_calls += 1
        params = {
            "ids": "channel==MINE",
            "startDate": start.isoformat(),
            "endDate": end.isoformat(),
            "metrics": ",".join(metrics),
            "dimensions": dimensions,
        }
        if filters:
            params["filters"] = filters
        await _ANALYTICS_RATE_LIMITER.acquire()
        async with self._analytics_gate:
            data = await self._get(ANALYTICS_API_URL, params)
        headers = [column["name"] for column in data.get("columnHeaders", [])]
        return [dict(zip(headers, row, strict=False)) for row in (data.get("rows") or [])]

    async def get_channel_analytics(self, start: date, end: date) -> dict:
        """Channel analytics over [start, end], with YPP detection.

        YPP (YouTube Partner Program) membership is detected by attempting the
        revenue metrics — non-monetized channels get a definitive 4xx and fall
        back to zeroed revenue. A transient failure proves nothing about
        monetization, so it propagates rather than mislabelling the channel.

        Raises:
            YouTubeTransientError: The revenue probe never got an answer.
        """
        try:
            core = await self._analytics_query(start, end, ["cpm", "averageViewPercentage"])
            ypp = True
        except YouTubeTransientError:
            raise
        except YouTubeApiError:
            core = await self._analytics_query(start, end, ["averageViewPercentage"])
            core["cpm"] = 0
            ypp = False

        day_metrics = ["views", "estimatedMinutesWatched"]
        if ypp:
            day_metrics.append("estimatedRedPartnerRevenue")
        daily = await self._analytics_query(start, end, day_metrics, dimensions="day")
        if not ypp:
            daily["estimatedRedPartnerRevenue"] = {}

        analytics = {**core, **daily, "ypp": ypp}
        analytics.update(await self._channel_reporting_metrics(start, end, ypp))
        return analytics

    async def _channel_reporting_metrics(self, start: date, end: date, ypp: bool) -> dict:
        """Channel figures nothing in scoring reads — the portal's channel stats.

        Kept apart from the scoring metrics above so a failure here can never
        affect acceptance or scores; each group degrades to absent on error.
        """
        reporting: dict = {}

        scalars = list(_CHANNEL_SCALAR_METRICS)
        day_metrics = list(_CHANNEL_DAY_METRICS)
        if ypp:
            scalars += _CHANNEL_SCALAR_METRICS_YPP
            day_metrics += _CHANNEL_DAY_METRICS_YPP

        async def group(metrics: list[str], dimensions: str | None) -> dict:
            try:
                return await self._analytics_query(start, end, metrics, dimensions=dimensions)
            except YouTubeApiError as err:
                bt.logging.warning(f"Channel reporting metrics unavailable: {err!r}")
                return {}

        groups, breakdowns = await asyncio.gather(
            asyncio.gather(group(scalars, None), group(day_metrics, "day")),
            self._gather_breakdowns(_CHANNEL_BREAKDOWNS, start, end, None, "Channel"),
        )
        for result in groups:
            reporting.update(result)
        reporting.update(breakdowns)
        return reporting

    # --- Videos ---------------------------------------------------------------

    async def get_all_uploads(self, max_age_days: int = YT_LOOKBACK) -> list[str]:
        """Ids of the channel's uploads within the age window (newest first).

        Walks the uploads playlist (1 credit/page); falls back to the search
        API (100 credits, cached) if the playlist is missing.
        """
        cutoff = datetime.now(UTC) - timedelta(days=max_age_days)
        channel = await self.get_channel_data(discrete_mode=False)
        playlist_id = channel.get("uploads_playlist")

        try:
            video_ids = await self._walk_uploads_playlist(playlist_id, cutoff)
        except YouTubeApiError as err:
            bt.logging.warning(f"Uploads playlist unavailable ({err}); falling back to search.")
            video_ids = await self._search_uploads(channel["_raw_channel_id"], cutoff)
        return video_ids[:YT_MAX_VIDEOS]

    async def _walk_uploads_playlist(self, playlist_id: str | None, cutoff: datetime) -> list[str]:
        if not playlist_id:
            raise YouTubeApiError("Channel has no uploads playlist")
        video_ids: list[str] = []
        page_token: str | None = None
        while True:
            self.data_api_calls += 1
            params = {"part": "snippet,contentDetails", "playlistId": playlist_id, "maxResults": 50}
            if page_token:
                params["pageToken"] = page_token
            data = await self._get(f"{DATA_API_URL}/playlistItems", params)
            for item in data.get("items", []):
                published = parse_timestamp(item["snippet"].get("publishedAt", ""))
                if published is not None and published < cutoff:
                    return video_ids
                video_ids.append(item["contentDetails"]["videoId"])
            page_token = data.get("nextPageToken")
            if not page_token:
                return video_ids

    async def _search_uploads(self, channel_id: str, cutoff: datetime) -> list[str]:
        if self._search_cache is not None:
            cached = self._search_cache.get(channel_id)
            if cached is not None:
                return cached

        video_ids: list[str] = []
        page_token: str | None = None
        for _ in range(2):  # search costs 100 credits per page; cap at ~100 videos
            self.data_api_calls += 100
            params = {
                "part": "id",
                "type": "video",
                "channelId": channel_id,
                "publishedAfter": cutoff.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "maxResults": 50,
                "order": "date",
            }
            if page_token:
                params["pageToken"] = page_token
            data = await self._get(f"{DATA_API_URL}/search", params)
            video_ids.extend(item["id"]["videoId"] for item in data.get("items", []) if "videoId" in item.get("id", {}))
            page_token = data.get("nextPageToken")
            if not page_token:
                break

        # Only persist a non-empty result: caching "no videos" for 12 h would
        # freeze a channel out of scoring on the strength of one bad answer.
        if self._search_cache is not None and video_ids:
            self._search_cache.set(channel_id, video_ids)
        return video_ids

    async def get_video_data_batch(self, video_ids: list[str], discrete_mode: bool = True) -> dict[str, dict]:
        """Snippet/statistics/status for up to 50 videos per API call."""
        results: dict[str, dict] = {}
        for offset in range(0, len(video_ids), _VIDEO_BATCH_SIZE):
            batch = video_ids[offset : offset + _VIDEO_BATCH_SIZE]
            self.data_api_calls += 1
            data = await self._get(
                f"{DATA_API_URL}/videos",
                {"part": "snippet,statistics,contentDetails,status", "id": ",".join(batch)},
            )
            for item in data.get("items", []):
                video_id = item["id"]
                results[video_id] = {
                    "videoId": video_id if not discrete_mode else None,
                    "bitcastVideoId": discrete_id(video_id),
                    "title": item["snippet"].get("title", ""),
                    "description": item["snippet"].get("description", ""),
                    "publishedAt": item["snippet"].get("publishedAt", ""),
                    "viewCount": item["statistics"].get("viewCount", "0"),
                    "likeCount": item["statistics"].get("likeCount", "0"),
                    "commentCount": item["statistics"].get("commentCount", "0"),
                    "duration": item["contentDetails"].get("duration", "PT0S"),
                    "caption": item["contentDetails"].get("caption", "false"),
                    "privacyStatus": item["status"].get("privacyStatus", "private"),
                }
        return results

    async def get_video_daily_analytics(self, video_id: str, start: date, end: date) -> list[dict]:
        """Per-day scoring metrics for one video, sorted by day.

        Only ever called for YPP accounts — a non-YPP account is ineligible and
        scores zero without reaching the Analytics API at all.
        """
        metrics = ["estimatedMinutesWatched", "estimatedRedPartnerRevenue"]
        daily = await self._analytics_query(start, end, metrics, dimensions="day", filters=f"video=={video_id}")

        by_day: dict[str, dict] = {}
        for metric, values in daily.items():
            for day, value in values.items():
                by_day.setdefault(day, {"day": day})[metric] = value
        return [by_day[day] for day in sorted(by_day)]

    async def get_video_daily_reporting(self, video_id: str, is_ypp: bool, start: date, end: date) -> list[dict]:
        """Per-day series for one video that scoring never reads.

        Deliberately separate from ``get_video_daily_analytics``: that list is
        the scoring input and must keep exactly the two metrics the curve
        consumes. These extras — including per-day breakdowns nested as
        ``{day: {dimension: value}}`` — travel alongside it so the dashboards
        get their time series back without touching the scoring path.
        """
        video_filter = f"video=={video_id}"
        by_day: dict[str, dict] = {}

        metrics = list(_VIDEO_DAY_METRICS) + (list(_VIDEO_DAY_METRICS_YPP) if is_ypp else [])

        async def scalars() -> dict:
            try:
                return await self._analytics_query(start, end, metrics, dimensions="day", filters=video_filter)
            except YouTubeApiError as err:
                bt.logging.warning(f"Video daily reporting metrics unavailable: {err!r}")
                return {}

        async def breakdown(key: str, metric: str, dimension: str) -> tuple[str, str, list[dict]]:
            try:
                rows = await self._analytics_rows(
                    start, end, [metric], dimensions=f"{dimension},day", filters=video_filter
                )
            except YouTubeApiError as err:
                bt.logging.warning(f"Video daily breakdown {key} unavailable: {err!r}")
                return key, dimension, []
            return key, dimension, rows

        daily, *breakdown_results = await asyncio.gather(
            scalars(), *(breakdown(*entry) for entry in _VIDEO_DAY_BREAKDOWNS)
        )
        for metric, values in daily.items():
            for day, value in values.items():
                by_day.setdefault(day, {"day": day})[metric] = value

        for key, dimension, rows in breakdown_results:
            metric = next(m for k, m, _ in _VIDEO_DAY_BREAKDOWNS if k == key)
            for row in rows:
                day, dimension_value = row.get("day"), row.get(dimension)
                if day is None or dimension_value is None or metric not in row:
                    continue
                by_day.setdefault(day, {"day": day}).setdefault(key, {})[dimension_value] = row[metric]

        return [by_day[day] for day in sorted(by_day)]

    async def get_video_analytics(self, video_id: str, is_ypp: bool, today: date | None = None) -> dict:
        """Aggregate lifetime analytics for one video, for reporting only.

        Nothing here feeds scoring — these are the engagement figures the
        creator portal and campaign dashboards render, so a failure degrades
        to a partial dict rather than failing the video's evaluation.

        Breakdowns cost one Analytics call each and are skipped in eco mode.
        """
        end = today or datetime.now(UTC).date()
        start = end - timedelta(days=_VIDEO_ANALYTICS_WINDOW)
        video_filter = f"video=={video_id}"

        metrics = ["views", "averageViewPercentage", "estimatedMinutesWatched", "shares"]
        if is_ypp:
            metrics += ["estimatedRedPartnerRevenue", "redViews", "estimatedRedMinutesWatched"]
        try:
            analytics = await self._analytics_query(start, end, metrics, filters=video_filter)
        except YouTubeApiError as err:
            bt.logging.warning(f"Video analytics unavailable: {err!r}")
            return {}

        if get_settings().eco_mode:
            return analytics

        results = await self._gather_breakdowns(
            _VIDEO_ANALYTICS_BREAKDOWNS, start, end, video_filter, "Video analytics"
        )
        analytics.update(results)
        return analytics

    async def _gather_breakdowns(
        self,
        breakdowns: tuple[tuple[str, str, str], ...],
        start: date,
        end: date,
        filters: str | None,
        label: str,
    ) -> dict:
        """Run independent breakdown reports concurrently, skipping any that fail.

        These are one report per (metric, dimension) with nothing shared
        between them, so issuing them in sequence just multiplies latency.
        """

        async def one(key: str, metric: str, dimension: str) -> tuple[str, dict | None]:
            try:
                result = await self._analytics_query(start, end, [metric], dimensions=dimension, filters=filters)
            except YouTubeApiError as err:
                bt.logging.warning(f"{label} breakdown {key} unavailable: {err!r}")
                return key, None
            return key, result.get(metric, {})

        pairs = await asyncio.gather(*(one(*breakdown) for breakdown in breakdowns))
        return {key: value for key, value in pairs if value is not None}


async def get_video_transcript(video_id: str, session: httpx.AsyncClient) -> list | None:
    """Fetch a video transcript via the RapidAPI transcriptor service.

    Returns a list of ``{"start", "dur", "text"}`` segments, or None when no
    transcript could be obtained after retries.
    """
    api_key = get_settings().rapid_api_key
    if not api_key:
        bt.logging.warning("RAPID_API_KEY not set; transcripts unavailable.")
        return None

    headers = {"x-rapidapi-key": api_key, "x-rapidapi-host": TRANSCRIPT_API_HOST}
    for attempt in range(TRANSCRIPT_MAX_RETRY):
        try:
            response = await session.get(
                TRANSCRIPT_API_URL,
                params={"video_id": video_id},
                headers=headers,
                timeout=5.0,
            )
            response.raise_for_status()
            data = response.json()
            if isinstance(data, list) and data and "transcription" in data[0]:
                return data[0]["transcription"]
            if isinstance(data, dict) and data.get("error") == "This video has no subtitles.":
                return None
        except (TimeoutError, httpx.HTTPError):
            pass
        if attempt < TRANSCRIPT_MAX_RETRY - 1:
            await asyncio.sleep(1)
    return None
