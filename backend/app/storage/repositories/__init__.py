"""Storage repository package.

Repository classes are imported from their concrete modules. Keeping package initialization
side-effect free prevents service and repository imports from forming a cycle.
"""
