import numpy as np
from bitcast.validator.reward import calculate_brief_emissions_scalar

# Define the burn rate and burn decay
max_burn = 0.9
burn_decay = 0.0001

# Define a range of total minutes watched
total_minutes_range = np.arange(0, 100000, 5000)

# Create a list of briefs with the same burn rate and decay
briefs = [{"id": f"brief_{i}", "max_burn": max_burn, "burn_decay": burn_decay} for i in range(1)]

# Prepare yt_stats_list for each scenario
yt_stats_list_scenarios = []
for total_minutes in total_minutes_range:
    yt_stats_list = [{"videos": [{"estimatedMinutesWatched": total_minutes, "matching_brief_ids": ["brief_0"]}]}]
    yt_stats_list_scenarios.append(yt_stats_list)

# Run calculate_brief_emissions_scalar for each scenario and print the results
for i, yt_stats_list in enumerate(yt_stats_list_scenarios):
    brief_scalars = calculate_brief_emissions_scalar(yt_stats_list, briefs)
    print(f"Scenario {i+1}: Total Minutes Watched = {total_minutes_range[i]}")
    print(f"Emission Scalars: {brief_scalars}\n")
