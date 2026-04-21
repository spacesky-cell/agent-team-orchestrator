"""Team memory module for shared context between agents.

Supports:
- Architecture Decision Records (ADRs)
- Code change summaries
- Semantic search for context retrieval
"""

import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

# Try to import chromadb for semantic search
try:
    import chromadb
    from chromadb.config import Settings as ChromaSettings
    HAS_CHROMA = True
except ImportError:
    HAS_CHROMA = False

# Configure logging
logger = logging.getLogger(__name__)


class DecisionRecord(BaseModel):
    """Architecture Decision Record (ADR)."""

    id: str = Field(..., description="Unique decision ID")
    title: str = Field(..., description="Decision title")
    content: str = Field(..., description="Decision content")
    agent_role: str = Field(..., description="Role of agent making the decision")
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())
    rationale: Optional[str] = Field(None, description="Rationale behind the decision")
    consequences: Optional[str] = Field(None, description="Consequences of the decision")


class CodeChange(BaseModel):
    """Code change record."""

    id: str = Field(..., description="Change ID")
    file_path: str = Field(..., description="Path to changed file")
    change_type: str = Field(..., description="Type: create, modify, delete")
    description: str = Field(..., description="Description of the change")
    agent_role: str = Field(..., description="Role of agent making the change")
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())
    snippet: Optional[str] = Field(None, description="Code snippet (first N lines)")


class TeamMemory:
    """Shared memory for multi-agent collaboration with semantic search.

    Features:
    - SQLite storage for structured metadata
    - ChromaDB for semantic search (optional)
    - Architecture Decision Records (ADRs)
    - Code change tracking
    - Context retrieval for agents
    """

    def __init__(
        self,
        project_root: str | Path = ".",
        storage_dir: str = ".ato/memory",
    ):
        """Initialize team memory.

        Args:
            project_root: Root directory of the project.
            storage_dir: Directory for memory storage (relative to project_root).
        """
        self.project_root = Path(project_root).resolve()
        self.storage_path = self.project_root / storage_dir
        self.storage_path.mkdir(parents=True, exist_ok=True)

        # SQLite for structured data
        self.db_path = self.storage_path / "memory.db"
        self._init_db()

        # ChromaDB for semantic search (optional)
        self._chroma_client = None
        self._decisions_collection = None
        self._changes_collection = None

        if HAS_CHROMA:
            self._init_chroma()

    def _init_db(self) -> None:
        """Initialize SQLite database."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Decisions table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS decisions (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                agent_role TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                rationale TEXT,
                consequences TEXT
            )
        """)

        # Code changes table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS code_changes (
                id TEXT PRIMARY KEY,
                file_path TEXT NOT NULL,
                change_type TEXT NOT NULL,
                description TEXT NOT NULL,
                agent_role TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                snippet TEXT
            )
        """)

        # Context table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS context (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)

        conn.commit()
        conn.close()

    def _init_chroma(self) -> None:
        """Initialize ChromaDB for semantic search."""
        try:
            chroma_path = self.storage_path / "chroma"
            self._chroma_client = chromadb.PersistentClient(
                path=str(chroma_path),
                settings=ChromaSettings(
                    anonymized_telemetry=False,
                    allow_reset=True,
                )
            )

            # Create collections
            self._decisions_collection = self._chroma_client.get_or_create_collection(
                name="decisions",
                metadata={"description": "Architecture decisions"}
            )
            self._changes_collection = self._chroma_client.get_or_create_collection(
                name="code_changes",
                metadata={"description": "Code change records"}
            )
        except Exception as e:
            logger.warning("Failed to initialize ChromaDB: %s", e)
            self._chroma_client = None
            self._decisions_collection = None
            self._changes_collection = None

    # ============ Decision Records ============

    def record_decision(
        self,
        title: str,
        content: str,
        agent_role: str,
        rationale: Optional[str] = None,
        consequences: Optional[str] = None,
    ) -> DecisionRecord:
        """Record a new architecture decision.

        Args:
            title: Decision title.
            content: Decision content.
            agent_role: Role of the agent making the decision.
            rationale: Optional rationale.
            consequences: Optional consequences.

        Returns:
            Created DecisionRecord.
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Generate ID
        cursor.execute("SELECT COUNT(*) FROM decisions")
        count = cursor.fetchone()[0]
        decision_id = f"dec-{count + 1}"

        timestamp = datetime.now().isoformat()

        cursor.execute(
            """
            INSERT INTO decisions
                (id, title, content, agent_role, timestamp, rationale, consequences)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (decision_id, title, content, agent_role, timestamp, rationale, consequences),
        )

        conn.commit()
        conn.close()

        # Add to ChromaDB for semantic search
        if self._decisions_collection is not None:
            try:
                self._decisions_collection.add(
                    ids=[decision_id],
                    documents=[f"{title}\n\n{content}\n\n{rationale or ''}"],
                    metadatas=[{
                        "title": title,
                        "agent_role": agent_role,
                        "timestamp": timestamp,
                    }]
                )
            except Exception as e:
                logger.warning("Failed to add to ChromaDB: %s", e)

        return DecisionRecord(
            id=decision_id,
            title=title,
            content=content,
            agent_role=agent_role,
            timestamp=timestamp,
            rationale=rationale,
            consequences=consequences,
        )

    def get_decisions(self, limit: int = 100) -> list[DecisionRecord]:
        """Get all decision records.

        Args:
            limit: Maximum number of records to return.

        Returns:
            List of DecisionRecord objects.
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute(
            "SELECT id, title, content, agent_role, timestamp, rationale, consequences "
            "FROM decisions ORDER BY timestamp DESC LIMIT ?",
            (limit,)
        )

        rows = cursor.fetchall()
        conn.close()

        return [
            DecisionRecord(
                id=row[0],
                title=row[1],
                content=row[2],
                agent_role=row[3],
                timestamp=row[4],
                rationale=row[5],
                consequences=row[6],
            )
            for row in rows
        ]

    def get_decisions_by_role(self, role: str) -> list[DecisionRecord]:
        """Get decisions made by a specific role.

        Args:
            role: Agent role to filter by.

        Returns:
            List of DecisionRecord objects.
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute(
            "SELECT id, title, content, agent_role, timestamp, rationale, consequences "
            "FROM decisions WHERE agent_role = ? ORDER BY timestamp DESC",
            (role,)
        )

        rows = cursor.fetchall()
        conn.close()

        return [
            DecisionRecord(
                id=row[0],
                title=row[1],
                content=row[2],
                agent_role=row[3],
                timestamp=row[4],
                rationale=row[5],
                consequences=row[6],
            )
            for row in rows
        ]

    # ============ Code Changes ============

    def record_code_change(
        self,
        file_path: str,
        change_type: str,
        description: str,
        agent_role: str,
        snippet: Optional[str] = None,
    ) -> CodeChange:
        """Record a code change.

        Args:
            file_path: Path to the changed file.
            change_type: Type of change (create, modify, delete).
            description: Description of the change.
            agent_role: Role of the agent making the change.
            snippet: Optional code snippet.

        Returns:
            Created CodeChange record.
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Generate ID
        cursor.execute("SELECT COUNT(*) FROM code_changes")
        count = cursor.fetchone()[0]
        change_id = f"chg-{count + 1}"

        timestamp = datetime.now().isoformat()

        cursor.execute(
            """
            INSERT INTO code_changes
                (id, file_path, change_type, description, agent_role, timestamp, snippet)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (change_id, file_path, change_type, description, agent_role, timestamp, snippet),
        )

        conn.commit()
        conn.close()

        # Add to ChromaDB for semantic search
        if self._changes_collection is not None:
            try:
                self._changes_collection.add(
                    ids=[change_id],
                    documents=[f"{file_path}\n\n{description}\n\n{snippet or ''}"],
                    metadatas=[{
                        "file_path": file_path,
                        "change_type": change_type,
                        "agent_role": agent_role,
                        "timestamp": timestamp,
                    }]
                )
            except Exception as e:
                logger.warning("Failed to add to ChromaDB: %s", e)

        return CodeChange(
            id=change_id,
            file_path=file_path,
            change_type=change_type,
            description=description,
            agent_role=agent_role,
            timestamp=timestamp,
            snippet=snippet,
        )

    def get_code_changes(self, limit: int = 100) -> list[CodeChange]:
        """Get all code change records.

        Args:
            limit: Maximum number of records to return.

        Returns:
            List of CodeChange objects.
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute(
            "SELECT id, file_path, change_type, description, agent_role, timestamp, snippet "
            "FROM code_changes ORDER BY timestamp DESC LIMIT ?",
            (limit,)
        )

        rows = cursor.fetchall()
        conn.close()

        return [
            CodeChange(
                id=row[0],
                file_path=row[1],
                change_type=row[2],
                description=row[3],
                agent_role=row[4],
                timestamp=row[5],
                snippet=row[6],
            )
            for row in rows
        ]

    # ============ Context Management ============

    def set_context(self, key: str, value: str) -> None:
        """Set a context value.

        Args:
            key: Context key.
            value: Context value.
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        timestamp = datetime.now().isoformat()
        cursor.execute(
            "INSERT OR REPLACE INTO context (key, value, updated_at) VALUES (?, ?, ?)",
            (key, value, timestamp)
        )

        conn.commit()
        conn.close()

    def get_context(self, key: str) -> Optional[str]:
        """Get a context value.

        Args:
            key: Context key.

        Returns:
            Context value or None if not found.
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("SELECT value FROM context WHERE key = ?", (key,))
        row = cursor.fetchone()
        conn.close()

        return row[0] if row else None

    def get_all_context(self) -> dict[str, str]:
        """Get all context values.

        Returns:
            Dictionary of context key-value pairs.
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("SELECT key, value FROM context")
        rows = cursor.fetchall()
        conn.close()

        return {row[0]: row[1] for row in rows}

    # ============ Semantic Search ============

    def retrieve_relevant_context(
        self,
        query: str,
        role: Optional[str] = None,
        top_k: int = 5,
    ) -> str:
        """Retrieve relevant context using semantic search.

        Args:
            query: Query string (e.g., task description).
            role: Optional role filter.
            top_k: Number of results to return.

        Returns:
            Formatted context string with relevant information.
        """
        lines = []

        # Use ChromaDB for semantic search if available
        if self._decisions_collection is not None:
            try:
                # Search decisions
                results = self._decisions_collection.query(
                    query_texts=[query],
                    n_results=top_k,
                )

                if results['ids'] and results['ids'][0]:
                    lines.append("## Relevant Architecture Decisions\n")
                    for i, doc_id in enumerate(results['ids'][0]):
                        metadata = results['metadatas'][0][i] if results['metadatas'] else {}
                        document = results['documents'][0][i] if results['documents'] else ""

                        lines.append(f"### {metadata.get('title', doc_id)}")
                        lines.append(document[:500])
                        lines.append(f"*By: {metadata.get('agent_role', 'unknown')}*\n")
            except Exception as e:
                logger.warning("ChromaDB search failed: %s", e)

        if self._changes_collection is not None:
            try:
                # Search code changes
                results = self._changes_collection.query(
                    query_texts=[query],
                    n_results=top_k,
                )

                if results['ids'] and results['ids'][0]:
                    lines.append("## Relevant Code Changes\n")
                    for i, doc_id in enumerate(results['ids'][0]):
                        metadata = results['metadatas'][0][i] if results['metadatas'] else {}
                        document = results['documents'][0][i] if results['documents'] else ""

                        lines.append(f"### {metadata.get('file_path', doc_id)}")
                        lines.append(
                            f"*{metadata.get('change_type', 'change')} "
                            f"by {metadata.get('agent_role', 'unknown')}*"
                        )
                        lines.append(document[:500])
                        lines.append("")
            except Exception as e:
                logger.warning("ChromaDB search failed: %s", e)

        # Fallback to simple keyword matching if ChromaDB not available
        if not lines:
            lines.append("## Recent Context (No Semantic Search)\n")

            # Add recent decisions
            decisions = self.get_decisions(limit=3)
            if decisions:
                lines.append("### Recent Decisions\n")
                for dec in decisions:
                    lines.append(f"- **{dec.title}**: {dec.content[:200]}...")

            # Add recent changes
            changes = self.get_code_changes(limit=5)
            if changes:
                lines.append("\n### Recent Changes\n")
                for change in changes:
                    lines.append(
                        f"- **{change.file_path}** "
                        f"({change.change_type}): {change.description}"
                    )

        if not lines:
            return "No previous context available."

        return "\n".join(lines)

    def get_context_for_agent(self, agent_role: str) -> str:
        """Generate context string for a specific agent role.

        Args:
            agent_role: Role of the agent requesting context.

        Returns:
            Formatted context string.
        """
        lines = []

        # Add decisions from architect (useful for all roles)
        architect_decisions = self.get_decisions_by_role("architect")
        if architect_decisions:
            lines.append("## Architecture Decisions\n")
            for dec in architect_decisions[-3:]:  # Last 3 decisions
                lines.append(f"### {dec.title}")
                lines.append(dec.content)
                if dec.rationale:
                    lines.append(f"**Rationale:** {dec.rationale}")
                lines.append("")

        # Add recent code changes
        recent_changes = self.get_code_changes(limit=5)
        if recent_changes:
            lines.append("## Recent Code Changes\n")
            for change in recent_changes:
                lines.append(f"- **{change.change_type}**: `{change.file_path}`")
                lines.append(f"  {change.description}")
                lines.append("")

        # Add shared context
        shared = self.get_all_context()
        if shared:
            lines.append("## Shared Context\n")
            for key, value in shared.items():
                lines.append(f"- **{key}**: {value}")
            lines.append("")

        if not lines:
            return "No previous context available."

        return "\n".join(lines)

    def clear(self) -> None:
        """Clear all memory data."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("DELETE FROM decisions")
        cursor.execute("DELETE FROM code_changes")
        cursor.execute("DELETE FROM context")

        conn.commit()
        conn.close()

        # Clear ChromaDB collections
        if self._chroma_client is not None:
            try:
                self._chroma_client.delete_collection("decisions")
                self._chroma_client.delete_collection("code_changes")
                self._init_chroma()  # Recreate empty collections
            except Exception:
                pass

    def summary(self) -> str:
        """Generate a summary of the memory contents.

        Returns:
            Summary string.
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM decisions")
        decisions = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM code_changes")
        changes = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM context")
        context_items = cursor.fetchone()[0]

        conn.close()

        return (
            f"Team Memory Summary:\n"
            f"- Architecture Decisions: {decisions}\n"
            f"- Code Changes: {changes}\n"
            f"- Context Items: {context_items}\n"
            f"- Storage: {self.storage_path}\n"
            f"- Semantic Search: {'Enabled (ChromaDB)' if HAS_CHROMA else 'Disabled'}"
        )
