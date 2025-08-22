"""Weight corrections publisher using unified API format."""

from typing import Dict, Any, List
import bittensor as bt
from .data_publisher import UnifiedDataPublisher


async def publish_weight_corrections(
    corrections: List[Dict[str, Any]],
    run_id: str,
    wallet: bt.wallet,
    endpoint: str
) -> bool:
    """
    Convenience function to publish weight corrections using unified API format.
    
    Args:
        corrections: List of weight correction items
        run_id: Validation cycle identifier
        wallet: Bittensor wallet for authentication
        endpoint: Weight corrections endpoint URL
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        bt.logging.info(f"🔄 Publishing {len(corrections)} weight corrections to {endpoint}")
        
        # Use UnifiedDataPublisher directly instead of wrapper
        publisher = UnifiedDataPublisher(wallet)
        success = await publisher.publish_unified_payload(
            payload_type="weight_corrections",
            run_id=run_id,
            payload_data=corrections,
            endpoint=endpoint
        )
        
        if success:
            bt.logging.info(f"✅ Weight corrections published for run {run_id}")
        else:
            bt.logging.warning(f"⚠️ Weight corrections publishing failed for run {run_id}")
            
        return success
            
    except Exception as e:
        bt.logging.error(f"Critical weight corrections publishing error: {e}")
        return False