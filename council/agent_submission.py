# -*- coding: utf-8 -*-
"""
agent_submission.py
Unified input interface for the Council of Experts.

AgentSubmission is the dataclass for submitting a system to be evaluated.
All three Experts share system_description.
Expert 1 requires an additional conversion to AgentProfile.
"""

from dataclasses import dataclass, field


@dataclass
class AgentSubmission:
    """
    Submission data for an AI system under evaluation.

    Fields:
        agent_id:           Unique identifier, used throughout the evaluation pipeline.
        system_description: Natural language description of the system, shared by all three Experts.
        system_name:        Display name used in reports.
        metadata:           Optional extra information (version, deployment environment, etc.)
    """
    agent_id:           str
    system_description: str
    system_name:        str = ""
    metadata:           dict = field(default_factory=dict)
    live_target_url:    str = ""   # non-empty → Expert 1 live attack mode
    incident_id:        str = ""   # pre-assigned by API layer; if empty, storage generates one

    def to_expert1_profile(self) -> dict:
        """
        Convert AgentSubmission into the AgentProfile dict required by Expert 1.

        Expert 1 needs: agent_id, name, description, purpose, deployment_context.
        purpose and deployment_context are extracted from metadata if provided,
        otherwise empty strings (Expert 1 infers them from description).

        Returns a plain dict to avoid circular imports.
        council_orchestrator.py handles the actual AgentProfile construction.
        """
        return {
            "agent_id":           self.agent_id,
            "name":               self.system_name or self.agent_id,
            "description":        self.system_description,
            "purpose":            self.metadata.get("purpose", ""),
            "deployment_context": self.metadata.get("deployment_context", ""),
            "data_access":        self.metadata.get("data_access", []),
            "risk_indicators":    self.metadata.get("risk_indicators", []),
        }
