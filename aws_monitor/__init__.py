"""
AWS Cost & Usage Monitor

An open-source tool for monitoring AWS costs and resource usage across
organizations.
"""

__version__ = "1.0.0"
__author__ = "Your Name"
__email__ = "your.email@example.com"

from .core.aws_client import AWSClient
from .core.cost_analyzer import CostAnalyzer
from .core.usage_tracker import UsageTracker
from .core.anomaly_detector import AnomalyDetector

__all__ = ["AWSClient", "CostAnalyzer", "UsageTracker", "AnomalyDetector"]
