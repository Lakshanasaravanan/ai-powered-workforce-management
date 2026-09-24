package com.slams.service;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.slams.exception.BusinessRuleConflictException;
import com.slams.model.*;
import com.slams.repository.IdempotencyRecordRepository;
import java.time.LocalDateTime;
import java.util.function.Supplier;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.stereotype.Service;

@Service
public class IdempotencyService {
    public record Result<T>(T body, boolean replay) { }
    private final IdempotencyRecordRepository records;
    private final ObjectMapper objectMapper;
    public IdempotencyService(IdempotencyRecordRepository records, ObjectMapper objectMapper) { this.records = records; this.objectMapper = objectMapper; }

    public <T> Result<T> execute(String key, User user, String operation, String payloadHash, Class<T> type, Supplier<T> mutation) {
        var existing = records.findByIdempotencyKey(key);
        if (existing.isPresent()) {
            IdempotencyRecord record = existing.get();
            if (!record.getUser().getId().equals(user.getId()) || !record.getOperation().equals(operation) || !record.getPayloadHash().equals(payloadHash))
                throw new BusinessRuleConflictException("IDEMPOTENCY_CONFLICT", "Idempotency key cannot be reused for a different request");
            if (record.getState() != IdempotencyState.COMPLETED)
                throw new BusinessRuleConflictException("IDEMPOTENCY_IN_PROGRESS", "Request is already being processed");
            try { return new Result<>(objectMapper.readValue(record.getResponseBody(), type), true); }
            catch (Exception exception) { throw new IllegalStateException("Stored idempotency response is unavailable", exception); }
        }
        try {
            records.saveAndFlush(IdempotencyRecord.builder().idempotencyKey(key).user(user).operation(operation).payloadHash(payloadHash)
                    .state(IdempotencyState.IN_PROGRESS).createdAt(LocalDateTime.now()).build());
        } catch (DataIntegrityViolationException collision) {
            throw new BusinessRuleConflictException("IDEMPOTENCY_IN_PROGRESS", "Request is already being processed");
        }
        T body = mutation.get();
        IdempotencyRecord record = records.findByIdempotencyKey(key).orElseThrow();
        try {
            record.setResponseBody(objectMapper.writeValueAsString(body)); record.setResponseStatus(200);
            record.setState(IdempotencyState.COMPLETED); record.setCompletedAt(LocalDateTime.now()); records.save(record);
        } catch (Exception exception) { throw new IllegalStateException("Unable to persist idempotency response", exception); }
        return new Result<>(body, false);
    }
}
