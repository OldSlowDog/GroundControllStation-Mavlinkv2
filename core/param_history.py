"""
Parameter History Manager
Version control system for flight controller parameters
Records every save operation with timestamp, description, and full parameter snapshot
Supports: version history, diff comparison, rollback, export/import
"""

import json
import os
import shutil
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field, asdict
from collections import OrderedDict


@dataclass
class ParamVersion:
    """Single parameter version snapshot"""
    version_id: int                    # Version number (auto-increment)
    timestamp: str                     # ISO format timestamp
    description: str                   # User-provided description (e.g., "Tuned for windy day")
    params: Dict[str, Any]            # Complete parameter dictionary {name: value}
    metadata: Dict[str, Any] = field(default_factory=dict)  # Extra info (FC info, etc.)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> 'ParamVersion':
        return cls(**data)


class ParamHistoryManager:
    """
    Parameter version history manager
    
    Features:
      - Auto-save on every parameter commit
      - Unlimited versions (configurable max)
      - Diff comparison between versions
      - Rollback to any previous version
      - Export/Import for backup
      - JSON file storage in logs/params_history/
    
    Storage location:
      GroundControlStation/logs/params_history/
      └── param_history.json  (main database)
      
    Format:
    {
        "current_version": 5,
        "max_versions": 50,
        "versions": [
            {
                "version_id": 1,
                "timestamp": "2026-05-01T22:30:15",
                "description": "Initial factory defaults",
                "params": {"PID_RATE_ROLL_P": 4.5, ...},
                "metadata": {...}
            },
            ...
        ]
    }
    """
    
    def __init__(self, max_versions: int = 50):
        self.max_versions = max_versions
        self.history_file = os.path.join("logs", "params_history", "param_history.json")
        self.current_version = 0
        self.versions: List[ParamVersion] = []
        
        self._ensure_directory()
        self._load_history()
    
    def _ensure_directory(self):
        """Create history directory if not exists"""
        os.makedirs(os.path.dirname(self.history_file), exist_ok=True)
    
    def _load_history(self):
        """Load history from JSON file"""
        if not os.path.exists(self.history_file):
            self._create_initial_version()
            return
        
        try:
            with open(self.history_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            self.current_version = data.get('current_version', 0)
            self.max_versions = data.get('max_versions', self.max_versions)
            
            self.versions = [
                ParamVersion.from_dict(v) 
                for v in data.get('versions', [])
            ]
            
        except (json.JSONDecodeError, KeyError, Exception) as e:
            print(f"[ParamHistory] Load error: {e}")
            self._create_initial_version()
    
    def _save_history(self):
        """Save history to JSON file"""
        data = {
            'current_version': self.current_version,
            'max_versions': self.max_versions,
            'versions': [v.to_dict() for v in self.versions]
        }
        
        # Atomic write: write to temp file first, then rename
        temp_file = self.history_file + '.tmp'
        try:
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            # Replace original file
            if os.path.exists(self.history_file):
                os.replace(temp_file, self.history_file)
            else:
                os.rename(temp_file, self.history_file)
                
        except Exception as e:
            print(f"[ParamHistory] Save error: {e}")
            if os.path.exists(temp_file):
                os.remove(temp_file)
    
    def _create_initial_version(self):
        """Create initial version with empty/default params"""
        initial = ParamVersion(
            version_id=1,
            timestamp=datetime.now().isoformat(),
            description="Initial version (no parameters)",
            params={},
            metadata={'auto_created': True}
        )
        self.versions.append(initial)
        self.current_version = 1
        self._save_history()
    
    def save_version(self, params: Dict[str, Any], 
                     description: str = "",
                     metadata: Optional[Dict] = None) -> int:
        """
        Save a new parameter version
        
        Args:
            params: Complete parameter dictionary {name: value}
            description: User description for this version
            metadata: Additional metadata (FC info, etc.)
        
        Returns:
            New version ID
        """
        self.current_version += 1
        
        new_version = ParamVersion(
            version_id=self.current_version,
            timestamp=datetime.now().isoformat(),
            description=description or f"Version {self.current_version}",
            params=dict(params),  # Copy to avoid reference issues
            metadata=metadata or {}
        )
        
        self.versions.append(new_version)
        
        # Enforce maximum versions limit (remove oldest)
        while len(self.versions) > self.max_versions:
            removed = self.versions.pop(0)
            print(f"[ParamHistory] Removed old version {removed.version_id}")
        
        self._save_history()
        
        print(f"[ParamHistory] Saved version {self.current_version}: {description[:30]}")
        return self.current_version
    
    def get_version(self, version_id: int) -> Optional[ParamVersion]:
        """Get specific version by ID"""
        for v in self.versions:
            if v.version_id == version_id:
                return v
        return None
    
    def get_latest_version(self) -> Optional[ParamVersion]:
        """Get the latest saved version"""
        return self.versions[-1] if self.versions else None
    
    def get_previous_version(self, current_id: int) -> Optional[ParamVersion]:
        """Get the version before specified one"""
        for i, v in enumerate(self.versions):
            if v.version_id == current_id and i > 0:
                return self.versions[i - 1]
        return None
    
    def get_all_versions(self) -> List[ParamVersion]:
        """Return all versions (newest first)"""
        return list(reversed(self.versions))
    
    def compare_versions(self, version1_id: int, version2_id: int) -> Dict[str, Dict]:
        """
        Compare two versions and return differences
        
        Returns:
            Dictionary of changed parameters:
            {
                'param_name': {
                    'v1_value': ...,
                    'v2_value': ...,
                    'changed': True/False
                }
            }
        """
        v1 = self.get_version(version1_id)
        v2 = self.get_version(version2_id)
        
        if not v1 or not v2:
            return {}
        
        all_keys = set(v1.params.keys()) | set(v2.params.keys())
        diffs = {}
        
        for key in sorted(all_keys):
            val1 = v1.params.get(key, '<not set>')
            val2 = v2.params.get(key, '<not set>')
            
            diffs[key] = {
                f'v{version1_id}': val1,
                f'v{version2_id}': val2,
                'changed': val1 != val2
            }
        
        return diffs
    
    def get_rollback_data(self, target_version_id: int) -> Optional[Dict[str, Any]]:
        """
        Get parameters from a specific version for rollback
        
        Returns:
            Parameter dict if found, None otherwise
        """
        version = self.get_version(target_version_id)
        if version:
            return dict(version.params)
        return None
    
    def export_history(self, filepath: str) -> bool:
        """
        Export entire history to file (for backup)
        
        Args:
            filepath: Output file path (.json)
        
        Returns:
            Success status
        """
        try:
            data = {
                'export_time': datetime.now().isoformat(),
                'source_file': self.history_file,
                'total_versions': len(self.versions),
                'current_version': self.current_version,
                'versions': [v.to_dict() for v in self.versions]
            }
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            print(f"[ParamHistory] Exported {len(self.versions)} versions to {filepath}")
            return True
            
        except Exception as e:
            print(f"[ParamHistory] Export failed: {e}")
            return False
    
    def import_history(self, filepath: str, merge: bool = False) -> bool:
        """
        Import history from backup file
        
        Args:
            filepath: Input file path
            merge: If True, append to existing; if False, replace entirely
        
        Returns:
            Success status
        """
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            imported_versions = [
                ParamVersion.from_dict(v) 
                for v in data.get('versions', [])
            ]
            
            if not merge:
                # Replace entire history
                self.versions = imported_versions
            else:
                # Merge: add only new versions (by version_id)
                existing_ids = {v.version_id for v in self.versions}
                for v in imported_versions:
                    if v.version_id not in existing_ids:
                        self.versions.append(v)
                
                # Sort by version_id
                self.versions.sort(key=lambda x: x.version_id)
            
            if self.versions:
                self.current_version = max(v.version_id for v in self.versions)
            
            self._save_history()
            print(f"[ParamHistory] Imported {len(imported_versions)} versions from {filepath}")
            return True
            
        except Exception as e:
            print(f"[ParamHistory] Import failed: {e}")
            return False
    
    def delete_version(self, version_id: int) -> bool:
        """
        Delete a specific version from history
        
        Warning: Cannot delete the only remaining version!
        """
        if len(self.versions) <= 1:
            print("[ParamHistory] Cannot delete: must keep at least one version")
            return False
        
        for i, v in enumerate(self.versions):
            if v.version_id == version_id:
                deleted = self.versions.pop(i)
                print(f"[ParamHistory] Deleted version {version_id}: {deleted.description}")
                self._save_history()
                return True
        
        return False
    
    def clear_all_history(self) -> bool:
        """Clear all history and start fresh"""
        if len(self.versions) <= 1:
            return False
        
        # Keep only the latest version
        latest = self.versions[-1]
        self.versions = [latest]
        self.current_version = latest.version_id
        self._save_history()
        
        print(f"[ParamHistory] Cleared history, kept version {latest.version_id}")
        return True
    
    def get_statistics(self) -> Dict[str, Any]:
        """Return usage statistics"""
        if not self.versions:
            return {'total': 0}
        
        total_params = len(self.versions[-1].params) if self.versions else 0
        
        return {
            'total_versions': len(self.versions),
            'current_version': self.current_version,
            'first_save': self.versions[0].timestamp if self.versions else None,
            'last_save': self.versions[-1].timestamp if self.versions else None,
            'total_params': total_params,
            'storage_size_kb': os.path.getsize(self.history_file) / 1024 if os.path.exists(self.history_file) else 0,
            'max_versions_limit': self.max_versions,
            'remaining_slots': self.max_versions - len(self.versions)
        }


# Global singleton instance
_param_history_manager: Optional[ParamHistoryManager] = None


def get_param_history() -> ParamHistoryManager:
    """Get or create global parameter history manager instance"""
    global _param_history_manager
    if _param_history_manager is None:
        _param_history_manager = ParamHistoryManager()
    return _param_history_manager
