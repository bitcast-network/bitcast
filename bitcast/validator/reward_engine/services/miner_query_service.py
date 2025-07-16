"""Handles communication with miners - extracted from get_rewards()."""

import asyncio
from typing import List, Dict
import bittensor as bt
from bitcast.protocol import AccessTokenSynapse
from ..models.miner_response import MinerResponse


class MinerQueryService:
    """Handles querying miners for access tokens."""
    
    async def query_miners(
        self, 
        validator_self, 
        uids: List[int]
    ) -> Dict[int, MinerResponse]:
        """
        Query all miners in parallel for better performance.
        
        Returns:
            Dict of {uid: MinerResponse} 
        """
        bt.logging.info(f"Querying {len(uids)} miners in parallel")
        
        # Create tasks for parallel execution
        tasks = [
            self._query_single_miner_safe(validator_self, uid) 
            for uid in uids
        ]
        
        # Execute all queries in parallel
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Process results
        responses = {}
        for uid, result in zip(uids, results):
            if isinstance(result, Exception):
                bt.logging.error(f"Error querying miner UID {uid}: {result}")
                responses[uid] = MinerResponse.create_error(uid, str(result))
            else:
                responses[uid] = result
        
        bt.logging.info(f"Completed querying {len(uids)} miners")
        return responses
    
    async def _query_single_miner_safe(self, validator_self, uid: int) -> MinerResponse:
        """Safely query a single miner with error handling."""
        try:
            response = await self._query_single_miner(validator_self, uid)
            return MinerResponse.from_response(uid, response)
        except Exception as e:
            bt.logging.error(f"Error querying miner UID {uid}: {e}")
            return MinerResponse.create_error(uid, str(e))
    
    async def _query_single_miner(self, validator_self, uid: int):
        """Query a single miner - extracted from query_miner()."""
        bt.logging.debug(f"Querying UID {uid}")
        
        response = await validator_self.dendrite(
            axons=[validator_self.metagraph.axons[uid]],
            synapse=AccessTokenSynapse(),
            deserialize=False,
        )
        
        miner_response = response[0] if response else None
        bt.logging.debug(f"Received response from UID {uid}")
        return miner_response 