"""
audit — tamper-evident action log.

The SHA-256 hash chain from the original build is preserved unchanged in
substance: each block commits to its predecessor, so editing any past entry
invalidates every hash after it. Extended here with the structured action
vocabulary the specification calls for (§16), while keeping the original
`record(officer, action)` signature working.
"""
from backend.audit.chain import AuditChain, ACTIONS

__all__ = ["AuditChain", "ACTIONS"]
