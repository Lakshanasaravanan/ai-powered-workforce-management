package com.slams.idempotency;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.slams.dto.LeaveApplicationResponse;
import com.slams.exception.BusinessRuleConflictException;
import com.slams.model.IdempotencyRecord;
import com.slams.model.IdempotencyState;
import com.slams.model.User;
import com.slams.repository.IdempotencyRecordRepository;
import com.slams.service.IdempotencyService;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.util.Optional;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;
import org.mockito.Mockito;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

class IdempotencyServiceTest {
    @Test
    void completedSamePayloadReplaysWithoutExecutingMutation() throws Exception {
        IdempotencyRecordRepository records = mock(IdempotencyRecordRepository.class);
        ObjectMapper mapper = mock(ObjectMapper.class);
        User user = mock(User.class); when(user.getId()).thenReturn(7L);
        LeaveApplicationResponse response = new LeaveApplicationResponse(1L, "PENDING", "CASUAL", LocalDate.now(), LocalDate.now(), LocalDateTime.now(), false);
        IdempotencyRecord record = IdempotencyRecord.builder().idempotencyKey("key").user(user).operation("LEAVE_APPLY").payloadHash("hash")
                .state(IdempotencyState.COMPLETED).responseBody("stored").build();
        when(records.findByIdempotencyKey("key")).thenReturn(Optional.of(record));
        when(mapper.readValue("stored", LeaveApplicationResponse.class)).thenReturn(response);
        AtomicInteger calls = new AtomicInteger();
        var result = new IdempotencyService(records, mapper).execute("key", user, "LEAVE_APPLY", "hash", LeaveApplicationResponse.class, () -> { calls.incrementAndGet(); return response; });
        assertTrue(result.replay()); assertEquals(0, calls.get()); assertEquals(1L, result.body().leaveRequestId());
    }

    @Test
    void sameKeyDifferentPayloadIsConflictAndNeverMutates() {
        IdempotencyRecordRepository records = mock(IdempotencyRecordRepository.class);
        ObjectMapper mapper = mock(ObjectMapper.class);
        User user = mock(User.class); when(user.getId()).thenReturn(7L);
        IdempotencyRecord record = IdempotencyRecord.builder().idempotencyKey("key").user(user).operation("LEAVE_APPLY").payloadHash("old").state(IdempotencyState.COMPLETED).build();
        when(records.findByIdempotencyKey("key")).thenReturn(Optional.of(record));
        AtomicInteger calls = new AtomicInteger();
        BusinessRuleConflictException error = assertThrows(BusinessRuleConflictException.class,
                () -> new IdempotencyService(records, mapper).execute("key", user, "LEAVE_APPLY", "new", LeaveApplicationResponse.class, () -> { calls.incrementAndGet(); return null; }));
        assertEquals("IDEMPOTENCY_CONFLICT", error.getCode()); assertEquals(0, calls.get());
    }
}
