import json
import hashlib
import re

# キー生成用の定数はそのまま維持
KEY_INTRA_PREFIX = "l"
KEY_INTER_PREFIX = "t"
KEY_PEER_PREFIX = "R_idx"

def create_dfmm_node_name(target_idx, level, node_idx):
    return f"mixer_t{target_idx}_l{level}_k{node_idx}"

def create_intra_key(level, node_idx):
    return f"{KEY_INTRA_PREFIX}{level}k{node_idx}"

def create_inter_key(target_idx, level, node_idx):
    return f"{KEY_INTER_PREFIX}{target_idx}_l{level}k{node_idx}"

def create_peer_key(peer_idx):
    return f"{KEY_PEER_PREFIX}{peer_idx}"

def parse_sharing_key(key_str_no_prefix):
    if key_str_no_prefix.startswith(KEY_PEER_PREFIX):
        return {
            "type": "PEER",
            "idx": int(key_str_no_prefix.replace(KEY_PEER_PREFIX, "")),
        }
    elif key_str_no_prefix.startswith(KEY_INTER_PREFIX):
        match = re.match(r"t(\d+)_l(\d+)k(\d+)", key_str_no_prefix)
        if match:
            return {
                "type": "DFMM",
                "target_idx": int(match.group(1)),
                "level": int(match.group(2)),
                "node_idx": int(match.group(3)),
            }
    elif key_str_no_prefix.startswith(KEY_INTRA_PREFIX):
        match = re.match(r"l(\d+)k(\d+)", key_str_no_prefix)
        if match:
            return {
                "type": "INTRA",
                "level": int(match.group(1)),
                "node_idx": int(match.group(2)),
            }
    raise ValueError(f"Unknown sharing key format: {key_str_no_prefix}")

def generate_config_hash(targets_config, mode, run_name):
    config_str = json.dumps(targets_config, sort_keys=True)
    full_string = f"{run_name}-{config_str}-{mode}"
    hasher = hashlib.md5()
    hasher.update(full_string.encode("utf-8"))
    return hasher.hexdigest()