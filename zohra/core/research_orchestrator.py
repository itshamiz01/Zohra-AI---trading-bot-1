"""
╔══════════════════════════════════════════════════════════════════════╗
║                 ZOHRA — RESEARCH ORCHESTRATOR                        ║
║         Multi-Agent Parallel Execution & Knowledge Ingestion        ║
╚══════════════════════════════════════════════════════════════════════╝
"""

import logging
import asyncio
import hashlib
from datetime import datetime
from typing import Dict, List, Any
from zohra.agents.academic_research_agent import academic_research_agent
from zohra.agents.internet_research_agent import internet_research_agent
from zohra.core.research_memory import research_memory
from zohra.core.knowledge_graph import knowledge_graph_engine
from zohra.core.fact_verification import fact_verification_engine
from zohra.core.report_generator import report_generator

logger = logging.getLogger("zohra.research.orchestrator")

class ResearchOrchestrator:
    """
    Coordinates multi-agent research tasks, processes the results through
    the verification and extraction layers, and updates the knowledge base.
    """
    async def conduct_research(self, topic: str, project_name: str = None) -> Dict[str, Any]:
        logger.info(f"🎓 Starting research task on topic: {topic}")
        
        # 1. Initialize Project
        if not project_name:
            project_name = f"Project_{topic.replace(' ', '_')}"
        project_id = hashlib.md5(project_name.encode()).hexdigest()[:8]
        research_memory.create_project(project_id, project_name, f"Research project focused on {topic}.")

        # 2. Run academic and web search agents in parallel
        loop = asyncio.get_event_loop()
        academic_task = loop.run_in_executor(None, academic_research_agent.search_papers, topic, 4)
        internet_task = loop.run_in_executor(None, internet_research_agent.search_web, topic, 4)
        
        academic_sources, internet_sources = await asyncio.gather(academic_task, internet_task)
        
        # Merge sources
        all_sources = academic_sources + internet_sources
        logger.info(f"Retrieved {len(all_sources)} sources for '{topic}'.")

        # 3. Save sources to memory
        for idx, src in enumerate(all_sources):
            src_id = f"src_{project_id}_{idx}"
            content = src.get("summary") or src.get("description") or ""
            research_memory.add_source(
                source_id=src_id,
                project_id=project_id,
                source_type="PDF" if "ArXiv" in src.get("source", "") else "WEBSITE",
                title=src.get("title"),
                author=", ".join(src.get("authors")) if isinstance(src.get("authors"), list) else src.get("author", "Unknown"),
                url=src.get("pdf_url") or src.get("url") or "",
                content=content
            )
            
            # Generate pseudo-embedding and save chunk
            emb = research_memory.generate_simple_embedding(content)
            research_memory.add_vector_chunk(f"chunk_{src_id}", src_id, content, emb)

        # 4. Extract and Verify Claims (Heuristic-based extraction of key sentences)
        claims = self._extract_claims_heuristics(all_sources)
        verified_claims = []
        for claim in claims:
            ver = fact_verification_engine.verify_claim(claim, all_sources)
            verified_claims.append(ver)

        # 5. Build Knowledge Graph linkages
        topic_node_id = topic.lower().replace(' ', '_')
        knowledge_graph_engine.add_node(topic_node_id, topic.capitalize(), "Research Topic", f"Core research topic on {topic}.")
        
        for src in all_sources:
            src_title = src.get("title", "")
            if src_title:
                node_id = src_title.lower().replace(' ', '_')[:30]
                knowledge_graph_engine.add_node(node_id, src_title[:30], "Source", f"Source: {src_title}")
                knowledge_graph_engine.add_edge(topic_node_id, node_id, "supported_by")

        # 6. Generate Report
        report_md = report_generator.generate_report(topic, all_sources, verified_claims, project_id)
        
        # Save report to sources as a generated file
        report_id = f"rep_{project_id}_{int(datetime.utcnow().timestamp())}"
        research_memory.add_source(
            source_id=report_id,
            project_id=project_id,
            source_type="NEWS",
            title=f"Intelligence Report: {topic}",
            author="Zohra Research Orchestrator",
            url="",
            content=report_md
        )

        try:
            from zohra.core.cognitive_memory import cognitive_memory
            cognitive_memory.add_timeline_event(
                event_type="RESEARCH_COMPLETED",
                description=f"Completed research on topic: '{topic}' with {len(all_sources)} sources and {len(verified_claims)} verified claims.",
                reference_id=project_id
            )
        except Exception as e:
            logger.error(f"Error logging research to timeline: {e}")

        return {
            "project_id": project_id,
            "project_name": project_name,
            "report_md": report_md,
            "sources_count": len(all_sources),
            "claims_count": len(verified_claims)
        }

    def _extract_claims_heuristics(self, sources: List[Dict[str, Any]]) -> List[str]:
        """Heuristically extracts key statements or summaries as claims to verify."""
        claims = []
        for src in sources:
            summary = src.get("summary", "")
            # Split into sentences
            sentences = [s.strip() for s in summary.split('.') if len(s.strip()) > 25]
            if sentences:
                # Add the first descriptive sentence as a claim
                claims.append(sentences[0])
        return list(set(claims))[:5] # Limit to top 5 unique claims

# Singleton
research_orchestrator = ResearchOrchestrator()
