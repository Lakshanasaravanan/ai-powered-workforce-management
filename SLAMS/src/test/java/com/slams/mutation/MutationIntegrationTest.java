package com.slams.mutation;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.slams.model.*;
import com.slams.repository.*;
import com.slams.service.AttendanceService;
import com.slams.service.LeaveService;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.LocalTime;
import java.util.UUID;
import java.util.concurrent.*;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest(properties = {"spring.datasource.url=jdbc:h2:mem:mutation-tests;DB_CLOSE_DELAY=-1", "spring.jpa.hibernate.ddl-auto=create-drop"})
@AutoConfigureMockMvc
class MutationIntegrationTest {
    @Autowired MockMvc mvc;
    @Autowired ObjectMapper json;
    @Autowired UserRepository users;
    @Autowired LeaveBalanceRepository balances;
    @Autowired LeaveRequestRepository leaves;
    @Autowired AttendanceRepository attendance;
    @Autowired AttendanceRegularizationRepository regularizations;
    @Autowired IdempotencyRecordRepository idempotency;
    @Autowired LeaveService leaveService;
    @Autowired AttendanceService attendanceService;

    private User employee;
    private User otherEmployee;
    private User manager;

    @BeforeEach
    void setUp() {
        idempotency.deleteAll(); regularizations.deleteAll(); leaves.deleteAll(); attendance.deleteAll(); balances.deleteAll();
        users.findByUsername("employee").ifPresent(users::delete);
        users.findByUsername("other").ifPresent(users::delete);
        employee = user("employee", Role.ROLE_EMPLOYEE);
        otherEmployee = user("other", Role.ROLE_EMPLOYEE);
        manager = users.findByUsername("manager").orElseThrow();
        balances.save(LeaveBalance.builder().user(employee).casualLeave(10).sickLeave(10).earnedLeave(10).build());
        balances.save(LeaveBalance.builder().user(otherEmployee).casualLeave(10).sickLeave(10).earnedLeave(10).build());
    }

    @Test @WithMockUser(username = "employee", roles = "EMPLOYEE")
    void leaveSuccessReplayAndPayloadConflictAreDeterministic() throws Exception {
        String key = UUID.randomUUID().toString();
        String body = leave("CASUAL", weekday(2), weekday(2), "medical appointment");
        mvc.perform(post("/api/leaves/apply").header("Idempotency-Key", key).contentType(MediaType.APPLICATION_JSON).content(body))
                .andExpect(status().isOk()).andExpect(jsonPath("$.idempotentReplay").value(false)).andExpect(jsonPath("$.status").value("PENDING"));
        mvc.perform(post("/api/leaves/apply").header("Idempotency-Key", key).contentType(MediaType.APPLICATION_JSON).content(body))
                .andExpect(status().isOk()).andExpect(jsonPath("$.idempotentReplay").value(true));
        assertThat(leaves.count()).isEqualTo(1);
        mvc.perform(post("/api/leaves/apply").header("Idempotency-Key", key).contentType(MediaType.APPLICATION_JSON)
                        .content(leave("CASUAL", weekday(3), weekday(3), "different payload")))
                .andExpect(status().isConflict()).andExpect(jsonPath("$.code").value("IDEMPOTENCY_CONFLICT"));
        assertThat(leaves.count()).isEqualTo(1);
    }

    @Test @WithMockUser(username = "employee", roles = "EMPLOYEE")
    void leaveRejectsMissingKeyValidationAndOverlapsWithoutMutation() throws Exception {
        mvc.perform(post("/api/leaves/apply").contentType(MediaType.APPLICATION_JSON).content(leave("CASUAL", weekday(2), weekday(2), "reason")))
                .andExpect(status().isBadRequest()).andExpect(jsonPath("$.code").value("IDEMPOTENCY_KEY_REQUIRED"));
        mvc.perform(post("/api/leaves/apply").header("Idempotency-Key", UUID.randomUUID()).contentType(MediaType.APPLICATION_JSON)
                        .content(leave("CASUAL", weekday(4), weekday(2), "reason")))
                .andExpect(status().isConflict()).andExpect(jsonPath("$.code").value("INVALID_LEAVE_DATE_RANGE"));
        String first = UUID.randomUUID().toString();
        mvc.perform(post("/api/leaves/apply").header("Idempotency-Key", first).contentType(MediaType.APPLICATION_JSON).content(leave("CASUAL", weekday(2), weekday(3), "reason"))).andExpect(status().isOk());
        mvc.perform(post("/api/leaves/apply").header("Idempotency-Key", UUID.randomUUID()).contentType(MediaType.APPLICATION_JSON).content(leave("CASUAL", weekday(3), weekday(4), "reason")))
                .andExpect(status().isConflict()).andExpect(jsonPath("$.code").value("LEAVE_OVERLAP"));
        assertThat(leaves.count()).isEqualTo(1);
    }

    @Test
    void approvalRechecksBalanceAndCannotBeRepeated() {
        LeaveRequest request = leaves.save(LeaveRequest.builder().user(employee).leaveType(LeaveType.CASUAL).startDate(weekday(2)).endDate(weekday(2)).status(LeaveStatus.PENDING).reason("reason").appliedAt(LocalDateTime.now()).build());
        LeaveBalance balance = balances.findByUserUsername("employee").orElseThrow();
        balance.setCasualLeave(0);
        balances.save(balance);
        assertThatThrownBy(() -> leaveService.updateStatus(request.getId(), LeaveStatus.APPROVED, "manager", null)).hasMessageContaining("Insufficient");
        assertThat(leaves.findById(request.getId()).orElseThrow().getStatus()).isEqualTo(LeaveStatus.PENDING);
    }

    @Test @WithMockUser(username = "employee", roles = "EMPLOYEE")
    void regularizationSuccessReplayConflictAndDuplicatePendingAreSafe() throws Exception {
        Attendance record = ownAttendance(employee);
        String key = UUID.randomUUID().toString();
        String body = regularization(record.getId(), "09:00:00", "17:00:00", "missed clock-in");
        mvc.perform(post("/api/attendance/regularize").header("Idempotency-Key", key).contentType(MediaType.APPLICATION_JSON).content(body))
                .andExpect(status().isOk()).andExpect(jsonPath("$.idempotentReplay").value(false));
        mvc.perform(post("/api/attendance/regularize").header("Idempotency-Key", key).contentType(MediaType.APPLICATION_JSON).content(body))
                .andExpect(status().isOk()).andExpect(jsonPath("$.idempotentReplay").value(true));
        mvc.perform(post("/api/attendance/regularize").header("Idempotency-Key", key).contentType(MediaType.APPLICATION_JSON)
                        .content(regularization(record.getId(), "09:01:00", "17:00:00", "changed")))
                .andExpect(status().isConflict()).andExpect(jsonPath("$.code").value("IDEMPOTENCY_CONFLICT"));
        mvc.perform(post("/api/attendance/regularize").header("Idempotency-Key", UUID.randomUUID()).contentType(MediaType.APPLICATION_JSON).content(body))
                .andExpect(status().isConflict()).andExpect(jsonPath("$.code").value("REGULARIZATION_ALREADY_PENDING"));
        assertThat(regularizations.count()).isEqualTo(1);
    }

    @Test @WithMockUser(username = "employee", roles = "EMPLOYEE")
    void regularizationEnforcesOwnershipTimeAndRequiredFields() throws Exception {
        Attendance foreign = ownAttendance(otherEmployee);
        mvc.perform(post("/api/attendance/regularize").header("Idempotency-Key", UUID.randomUUID()).contentType(MediaType.APPLICATION_JSON)
                        .content(regularization(foreign.getId(), "09:00:00", "17:00:00", "reason")))
                .andExpect(status().isNotFound());
        Attendance mine = ownAttendance(employee);
        mvc.perform(post("/api/attendance/regularize").header("Idempotency-Key", UUID.randomUUID()).contentType(MediaType.APPLICATION_JSON)
                        .content(regularization(mine.getId(), "17:00:00", "09:00:00", "reason")))
                .andExpect(status().isConflict()).andExpect(jsonPath("$.code").value("INVALID_REGULARIZATION_TIME_RANGE"));
        mvc.perform(post("/api/attendance/regularize").header("Idempotency-Key", UUID.randomUUID()).contentType(MediaType.APPLICATION_JSON)
                        .content("{\"attendanceId\":" + mine.getId() + ",\"requestedInTime\":\"09:00:00\"}"))
                .andExpect(status().isBadRequest()).andExpect(jsonPath("$.code").value("VALIDATION_ERROR"));
        assertThat(regularizations.count()).isZero();
    }

    @Test
    void regularizationDecisionRequiresPendingState() {
        Attendance record = ownAttendance(employee);
        AttendanceRegularization pending = regularizations.save(AttendanceRegularization.builder().attendance(record).requestedInTime(LocalTime.of(9, 0)).requestedOutTime(LocalTime.of(17, 0)).reason("reason").status(LeaveStatus.PENDING).requestedAt(LocalDateTime.now()).build());
        attendanceService.decideRegularization("manager", pending.getId(), LeaveStatus.APPROVED);
        assertThat(regularizations.findById(pending.getId()).orElseThrow().getStatus()).isEqualTo(LeaveStatus.APPROVED);
        assertThatThrownBy(() -> attendanceService.decideRegularization("manager", pending.getId(), LeaveStatus.APPROVED)).hasMessageContaining("Only pending");
    }

    @Test
    void concurrentSameKeyLeaveCreatesOneRequestAndAValidIdempotencyRecord() throws Exception {
        String key = UUID.randomUUID().toString();
        var request = new com.slams.dto.LeaveApplyRequest(LeaveType.CASUAL, weekday(2), weekday(2), "concurrent leave");
        var results = concurrently(() -> leaveService.applyLeave("employee", key, request), () -> leaveService.applyLeave("employee", key, request));
        assertSafeConcurrencyResults(results);
        assertThat(leaves.count()).isEqualTo(1);
        assertThat(results.stream().filter(this::isSuccess).count()).isGreaterThanOrEqualTo(1);
        assertThat(idempotency.findByIdempotencyKey(key).orElseThrow().getState()).isEqualTo(IdempotencyState.COMPLETED);
    }

    @Test
    void concurrentOverlappingLeavesLeaveOnlyOnePendingRequest() throws Exception {
        var one = new com.slams.dto.LeaveApplyRequest(LeaveType.CASUAL, weekday(2), weekday(3), "first");
        var two = new com.slams.dto.LeaveApplyRequest(LeaveType.CASUAL, weekday(3), weekday(4), "second");
        var results = concurrently(() -> leaveService.applyLeave("employee", UUID.randomUUID().toString(), one), () -> leaveService.applyLeave("employee", UUID.randomUUID().toString(), two));
        assertSafeConcurrencyResults(results);
        assertThat(leaves.count()).isEqualTo(1);
        assertThat(results.stream().filter(this::isSuccess).count()).isEqualTo(1);
    }

    @Test
    void concurrentSameKeyRegularizationCreatesOneRequest() throws Exception {
        Attendance record = ownAttendance(employee); String key = UUID.randomUUID().toString();
        var request = regularizationRequest(record.getId(), LocalTime.of(9, 0), LocalTime.of(17, 0), "concurrent");
        var results = concurrently(() -> attendanceService.requestRegularization("employee", key, request), () -> attendanceService.requestRegularization("employee", key, request));
        assertSafeConcurrencyResults(results);
        assertThat(regularizations.count()).isEqualTo(1);
        assertThat(results.stream().filter(this::isSuccess).count()).isGreaterThanOrEqualTo(1);
        assertThat(idempotency.findByIdempotencyKey(key).orElseThrow().getState()).isEqualTo(IdempotencyState.COMPLETED);
    }

    @Test
    void concurrentDifferentRegularizationsLeaveOnlyOnePendingRequest() throws Exception {
        Attendance record = ownAttendance(employee);
        var one = regularizationRequest(record.getId(), LocalTime.of(9, 0), LocalTime.of(17, 0), "first");
        var two = regularizationRequest(record.getId(), LocalTime.of(9, 15), LocalTime.of(17, 15), "second");
        var results = concurrently(() -> attendanceService.requestRegularization("employee", UUID.randomUUID().toString(), one), () -> attendanceService.requestRegularization("employee", UUID.randomUUID().toString(), two));
        assertSafeConcurrencyResults(results);
        assertThat(regularizations.count()).isEqualTo(1);
        assertThat(results.stream().filter(this::isSuccess).count()).isEqualTo(1);
    }

    private java.util.List<Object> concurrently(Callable<?> first, Callable<?> second) throws Exception {
        ExecutorService executor = Executors.newFixedThreadPool(2); CountDownLatch ready = new CountDownLatch(2); CountDownLatch start = new CountDownLatch(1);
        try {
            java.util.List<Future<Object>> futures = java.util.List.of(executor.submit(() -> invokeAtBarrier(first, ready, start)), executor.submit(() -> invokeAtBarrier(second, ready, start)));
            assertThat(ready.await(5, TimeUnit.SECONDS)).isTrue(); start.countDown();
            return futures.stream().map(f -> { try { return f.get(10, TimeUnit.SECONDS); } catch (Exception e) { return e; } }).toList();
        } finally { executor.shutdownNow(); }
    }
    private Object invokeAtBarrier(Callable<?> call, CountDownLatch ready, CountDownLatch start) { try { ready.countDown(); start.await(5, TimeUnit.SECONDS); return call.call(); } catch (Exception e) { return e; } }
    private boolean isSuccess(Object result) { return !(result instanceof Exception); }
    private void assertSafeConcurrencyResults(java.util.List<Object> results) {
        assertThat(results).allSatisfy(result -> {
            if (result instanceof Exception exception) {
                assertThat(exception).isInstanceOf(com.slams.exception.BusinessRuleConflictException.class);
            }
        });
    }
    private com.slams.dto.RegularizationRequest regularizationRequest(Long id, LocalTime in, LocalTime out, String reason) {
        var request = new com.slams.dto.RegularizationRequest(); request.setAttendanceId(id); request.setRequestedInTime(in); request.setRequestedOutTime(out); request.setReason(reason); return request;
    }

    private User user(String username, Role role) {
        return users.save(User.builder().username(username).password("test").email(username + "@example.test").fullName(username).employeeId("E" + username).role(role).status(UserStatus.ACTIVE).workMode(WorkMode.WFO).build());
    }
    private Attendance ownAttendance(User owner) { return attendance.save(Attendance.builder().user(owner).date(LocalDate.now().minusDays(1)).status(AttendanceStatus.ABSENT).build()); }
    private static LocalDate weekday(int offset) {
        LocalDate d = LocalDate.now().plusDays(1);
        while (d.getDayOfWeek() != java.time.DayOfWeek.MONDAY) d = d.plusDays(1);
        return d.plusDays(offset);
    }
    private String leave(String type, LocalDate start, LocalDate end, String reason) throws Exception { return json.writeValueAsString(java.util.Map.of("leaveType", type, "startDate", start, "endDate", end, "reason", reason)); }
    private String regularization(Long id, String in, String out, String reason) throws Exception { return json.writeValueAsString(java.util.Map.of("attendanceId", id, "requestedInTime", in, "requestedOutTime", out, "reason", reason)); }
}
