"""
Checkpoint system for saving and resuming processing
"""
import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class CheckpointManager:
    """Manage checkpoints for resuming interrupted processing"""
    
    CHECKPOINT_FILE = "checkpoint.json"
    
    def __init__(self, output_dir: Path):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        self.checkpoint_path = self.output_dir / self.CHECKPOINT_FILE
    
    def save_checkpoint(self, step: str, data: Dict[str, Any], metadata: Optional[Dict[str, Any]] = None):
        """Save checkpoint for a processing step"""
        checkpoint = {
            "step": step,
            "timestamp": datetime.now().isoformat(),
            "data": data,
            "metadata": metadata or {}
        }
        
        try:
            with open(self.checkpoint_path, 'w', encoding='utf-8') as f:
                json.dump(checkpoint, f, indent=2, ensure_ascii=False)
            logger.info(f"Checkpoint saved: {step}")
        except Exception as e:
            logger.error(f"Failed to save checkpoint: {e}")
    
    def load_checkpoint(self) -> Optional[Dict[str, Any]]:
        """Load latest checkpoint"""
        if not self.checkpoint_path.exists():
            return None
        
        try:
            with open(self.checkpoint_path, 'r', encoding='utf-8') as f:
                checkpoint = json.load(f)
            logger.info(f"Checkpoint loaded: {checkpoint.get('step', 'unknown')} from {checkpoint.get('timestamp', 'unknown')}")
            return checkpoint
        except Exception as e:
            logger.error(f"Failed to load checkpoint: {e}")
            return None
    
    def clear_checkpoint(self):
        """Clear checkpoint file"""
        if self.checkpoint_path.exists():
            try:
                self.checkpoint_path.unlink()
                logger.info("Checkpoint cleared")
            except Exception as e:
                logger.error(f"Failed to clear checkpoint: {e}")
    
    def save_step_result(self, step_name: str, result: Any, filename: Optional[str] = None):
        """Save step result to a separate file"""
        if filename is None:
            filename = f"{step_name}_result.json"
        
        result_path = self.output_dir / filename
        
        try:
            if isinstance(result, (dict, list)):
                with open(result_path, 'w', encoding='utf-8') as f:
                    json.dump(result, f, indent=2, ensure_ascii=False)
            elif isinstance(result, str):
                with open(result_path, 'w', encoding='utf-8') as f:
                    f.write(result)
            else:
                with open(result_path, 'w', encoding='utf-8') as f:
                    json.dump({"result": str(result)}, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Step result saved: {result_path}")
            return result_path
        except Exception as e:
            logger.error(f"Failed to save step result: {e}")
            return None
    
    def load_step_result(self, step_name: str, filename: Optional[str] = None) -> Optional[Any]:
        """Load step result from a separate file"""
        if filename is None:
            filename = f"{step_name}_result.json"
        
        result_path = self.output_dir / filename
        
        if not result_path.exists():
            return None
        
        try:
            if filename.endswith('.json'):
                with open(result_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            else:
                with open(result_path, 'r', encoding='utf-8') as f:
                    return f.read()
        except Exception as e:
            logger.error(f"Failed to load step result '{step_name}': {e}")
            return None
    
    def step_result_exists(self, step_name: str, filename: Optional[str] = None) -> bool:
        """Check if step result file exists"""
        if filename is None:
            filename = f"{step_name}_result.json"
        
        result_path = self.output_dir / filename
        return result_path.exists()

