# InfoTech Workspace architecture

```text
React Workspace -> EMS API -> PostgreSQL / Redis
                -> Agentic RAG service (future) -> Qdrant / OpenRouter (future)
```

The future agent never writes the database directly: user → agent → typed EMS API tool → authorization and business validation → database → confirmed result. Roles (`ADMIN`, `MANAGER`, `EMPLOYEE`) control authority; designations such as Senior Engineer and Team Lead are separate job attributes.
