from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


def get_utc_now():
    return datetime.now(timezone.utc)


class Project(Base):
    __tablename__ = "projects"

    id = Column(String(64), primary_key=True)
    name = Column(String(255), nullable=False)
    template = Column(String(64), default="react")
    owner_id = Column(String(64), default="default_user")
    created_at = Column(DateTime, default=get_utc_now)
    updated_at = Column(DateTime, default=get_utc_now, onupdate=get_utc_now)

    workspaces = relationship("Workspace", back_populates="project", cascade="all, delete-orphan")


class Workspace(Base):
    __tablename__ = "workspaces"

    id = Column(String(64), primary_key=True)
    project_id = Column(String(64), ForeignKey("projects.id"), nullable=False)
    status = Column(String(32), default="READY")  # CREATING, STARTING, READY, ACTIVE, IDLE, STOPPED, FAILED
    pod_name = Column(String(128), nullable=True)
    namespace = Column(String(64), default="default")
    last_active_at = Column(DateTime, default=get_utc_now)
    created_at = Column(DateTime, default=get_utc_now)

    project = relationship("Project", back_populates="workspaces")
    agent_runs = relationship("AgentRun", back_populates="workspace", cascade="all, delete-orphan")


class AgentRun(Base):
    __tablename__ = "agent_runs"

    id = Column(String(64), primary_key=True)
    workspace_id = Column(String(64), ForeignKey("workspaces.id"), nullable=False)
    session_id = Column(String(64), nullable=False)
    prompt = Column(Text, nullable=False)
    model = Column(String(64), default="gpt-4o")
    status = Column(String(32), default="RUNNING")  # RUNNING, COMPLETED, FAILED
    input_tokens = Column(Integer, default=0)
    output_tokens = Column(Integer, default=0)
    estimated_cost = Column(Float, default=0.0)
    duration_ms = Column(Integer, default=0)
    started_at = Column(DateTime, default=get_utc_now)
    completed_at = Column(DateTime, nullable=True)

    workspace = relationship("Workspace", back_populates="agent_runs")
    tool_calls = relationship("ToolCallRecord", back_populates="agent_run", cascade="all, delete-orphan")


class ToolCallRecord(Base):
    __tablename__ = "tool_calls"

    id = Column(String(64), primary_key=True)
    agent_run_id = Column(String(64), ForeignKey("agent_runs.id"), nullable=False)
    tool_name = Column(String(64), nullable=False)
    arguments_json = Column(Text, nullable=True)
    result_json = Column(Text, nullable=True)
    risk_level = Column(String(32), default="safe")
    success = Column(Boolean, default=True)
    duration_ms = Column(Integer, default=0)
    created_at = Column(DateTime, default=get_utc_now)

    agent_run = relationship("AgentRun", back_populates="tool_calls")
