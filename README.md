# AI-Powered Workforce Management

`SLAMS/` is the Spring Boot/Thymeleaf employee application and `RAG_Chatbot/` is the FastAPI agent service.

```text
Employee browser -> SLAMS UI -> server-side assistant proxy -> Agentic RAG
                                                        |-> FAISS policy retrieval
                                                        |-> Redis action state
                                                        |-> workforce provider --RS256--> SLAMS APIs -> MySQL
```

The browser never receives the assistant secret, delegation private key, database credentials, or a trusted employee ID. SLAMS derives identity from its authenticated session and its server-side proxy forwards chat using a short-lived assistant token.

Run backend tests with `cd RAG_Chatbot && PYTHONPATH=backend .venv/bin/pytest backend/tests -q`; run SLAMS tests with `cd SLAMS && mvn test && mvn package -DskipTests`. The root `compose.yaml` defines the production-like local topology; supply required secrets through the environment.
