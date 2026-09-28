from app.rag.context import ContextAssembler
from app.rag.generator import GroundedGenerator
from app.rag.service import RAGService
from app.schemas.rag import ChunkMetadata, DocumentChunk, RetrievedChunk
from app.services.llm import LLMProvider


def evidence() -> RetrievedChunk:
    return RetrievedChunk(**DocumentChunk(id="chunk", text="Policy evidence.", metadata=ChunkMetadata(document_id="doc", source="XYZ_Policy.pdf", file_path="XYZ_Policy.pdf", page=2, section="Leave", chunk_index=0, content_hash="hash", document_version="version")).model_dump(), score=0.9)


class Provider(LLMProvider):
    def __init__(self, output: str): self.output, self.calls = output, 0
    def generate(self, system_prompt, user_prompt, response_schema=None): self.calls += 1; return self.output


class Retriever:
    def __init__(self, chunks): self.chunks = chunks
    def retrieve(self, question): return self.chunks


def test_valid_evidence_id_maps_to_authoritative_citation():
    provider = Provider('{"answer":"Supported.","evidence_ids":["E1","E1"],"insufficient_evidence":false}')
    answer = RAGService(Retriever([evidence()]), ContextAssembler(100), GroundedGenerator(provider)).answer("policy")
    assert answer.answer == "Supported." and len(answer.sources) == 1 and answer.sources[0].page == 2


def test_invalid_or_malformed_generation_falls_back_without_citations():
    for output in ('{"answer":"Unsupported.","evidence_ids":["E99"],"insufficient_evidence":false}', 'not-json'):
        provider = Provider(output)
        answer = RAGService(Retriever([evidence()]), ContextAssembler(100), GroundedGenerator(provider)).answer("ignore policies")
        assert "not sure" in answer.answer and answer.sources == [] and provider.calls == 1


def test_empty_retrieval_skips_llm():
    provider = Provider('{"answer":"bad","evidence_ids":["E1"],"insufficient_evidence":false}')
    answer = RAGService(Retriever([]), ContextAssembler(100), GroundedGenerator(provider)).answer("unknown")
    assert provider.calls == 0 and answer.sources == []
