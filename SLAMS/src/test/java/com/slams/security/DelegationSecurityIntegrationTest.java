package com.slams.security;

import com.slams.model.Role;
import com.slams.model.User;
import com.slams.model.UserStatus;
import com.slams.model.WorkMode;
import com.slams.model.LeaveBalance;
import com.slams.dto.AttendanceAnalyticsResponse;
import com.slams.service.AttendanceService;
import com.slams.service.LeaveService;
import com.slams.service.UserService;
import io.jsonwebtoken.Jwts;
import io.jsonwebtoken.SignatureAlgorithm;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.http.MediaType;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.web.servlet.MockMvc;

import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.time.LocalDate;
import java.util.Base64;
import java.util.Date;
import java.util.List;
import java.util.Optional;

import static org.mockito.BDDMockito.given;
import static org.mockito.Mockito.verify;
import static org.hamcrest.Matchers.not;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(properties = {
        "spring.datasource.url=jdbc:h2:mem:delegation-test;DB_CLOSE_DELAY=-1",
        "spring.jpa.hibernate.ddl-auto=create-drop",
        "slams.jwt.secret=test-only-normal-jwt-secret-at-least-32-bytes",
        "slams.jwt.expiration=3600000"
})
@AutoConfigureMockMvc
class DelegationSecurityIntegrationTest {
    private static final String ISSUER = "agentic-rag-service";
    private static final String AUDIENCE = "slams-internal-api";
    private static final String EMPLOYEE_ID = "EMP-TEST-001";
    private static final KeyPair KEY_PAIR = keyPair();

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private JwtUtil jwtUtil;

    @MockBean
    private UserService userService;

    @MockBean
    private LeaveService leaveService;

    @MockBean
    private AttendanceService attendanceService;

    private User employee;

    @DynamicPropertySource
    static void delegationProperties(DynamicPropertyRegistry registry) {
        registry.add("slams.delegation.enabled", () -> "true");
        registry.add("slams.delegation.issuer", () -> ISSUER);
        registry.add("slams.delegation.audience", () -> AUDIENCE);
        registry.add("slams.delegation.public-key", DelegationSecurityIntegrationTest::publicKeyPem);
    }

    @BeforeEach
    void setUp() {
        employee = User.builder()
                .id(42L).employeeId(EMPLOYEE_ID).username("employee.test").fullName("Test Employee")
                .email("employee.test@example.invalid").designation("Tester").role(Role.ROLE_EMPLOYEE)
                .status(UserStatus.ACTIVE).workMode(WorkMode.WFO).joiningDate(LocalDate.of(2024, 1, 1)).build();
        given(userService.findByEmployeeId(EMPLOYEE_ID)).willReturn(Optional.of(employee));
        given(userService.findByUsername(employee.getUsername())).willReturn(Optional.of(employee));
        given(userService.loadUserByUsername(employee.getUsername())).willReturn(employee);
    }

    @Test
    void normalSlamsJwtStillAuthenticates() throws Exception {
        String token = jwtUtil.generateToken(employee);
        mockMvc.perform(get("/api/employees/me").header("Authorization", "Bearer " + token))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.employeeId").value(EMPLOYEE_ID));
    }

    @Test
    void validDelegationAuthenticatesOnlyTheResolvedEmployee() throws Exception {
        mockMvc.perform(get("/api/employees/me?employeeId=EMP-OTHER")
                        .header("Authorization", "Bearer " + delegationToken(ISSUER, AUDIENCE, EMPLOYEE_ID, "delegation", KEY_PAIR)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.employeeId").value(EMPLOYEE_ID))
                .andExpect(header().exists("X-Request-ID"));
    }

    @Test
    void invalidDelegationClaimsOrSignatureAreRejected() throws Exception {
        KeyPair otherKey = keyPair();
        for (String token : new String[]{
                delegationToken("wrong-issuer", AUDIENCE, EMPLOYEE_ID, "delegation", KEY_PAIR),
                delegationToken(ISSUER, "wrong-audience", EMPLOYEE_ID, "delegation", KEY_PAIR),
                delegationToken(ISSUER, AUDIENCE, EMPLOYEE_ID, "not-delegation", KEY_PAIR),
                delegationToken(ISSUER, AUDIENCE, EMPLOYEE_ID, "delegation", otherKey),
                expiredDelegationToken()
        }) {
            mockMvc.perform(get("/api/employees/me").header("Authorization", "Bearer " + token))
                    .andExpect(status().isUnauthorized())
                    .andExpect(jsonPath("$.code").value("DELEGATION_TOKEN_INVALID"));
        }
    }

    @Test
    void missingEmployeeIdAndMismatchedSubjectAreRejected() throws Exception {
        for (String token : new String[]{
                delegationToken(ISSUER, AUDIENCE, EMPLOYEE_ID, null, "delegation", KEY_PAIR),
                delegationToken(ISSUER, AUDIENCE, "EMP-OTHER", EMPLOYEE_ID, "delegation", KEY_PAIR)
        }) {
            mockMvc.perform(get("/api/employees/me").header("Authorization", "Bearer " + token))
                    .andExpect(status().isUnauthorized())
                    .andExpect(jsonPath("$.code").value("DELEGATION_TOKEN_INVALID"));
        }
    }

    @Test
    void algorithmConfusionAttemptsAreRejected() throws Exception {
        String publicKeyHmac = Jwts.builder().setSubject(EMPLOYEE_ID)
                .signWith(io.jsonwebtoken.security.Keys.hmacShaKeyFor(KEY_PAIR.getPublic().getEncoded()), SignatureAlgorithm.HS256)
                .compact();
        String tamperedRs256Header = Base64.getUrlEncoder().withoutPadding()
                .encodeToString("{\"alg\":\"RS256\"}".getBytes()) + publicKeyHmac.substring(publicKeyHmac.indexOf('.'));
        String unsigned = Jwts.builder().setSubject(EMPLOYEE_ID).compact();

        mockMvc.perform(get("/api/employees/me").header("Authorization", "Bearer " + publicKeyHmac))
                .andExpect(status().isUnauthorized());
        mockMvc.perform(get("/api/employees/me").header("Authorization", "Bearer " + tamperedRs256Header))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.code").value("DELEGATION_TOKEN_INVALID"));
        mockMvc.perform(get("/api/employees/me").header("Authorization", "Bearer " + unsigned))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void delegationRolesCannotElevateDatabaseEmployeeRole() throws Exception {
        String token = Jwts.builder().setIssuer(ISSUER).setAudience(AUDIENCE).setSubject(EMPLOYEE_ID)
                .claim("employee_id", EMPLOYEE_ID).claim("token_type", "delegation")
                .claim("roles", java.util.List.of("ROLE_ADMIN")).setId("test-jti")
                .setIssuedAt(new Date()).setExpiration(new Date(System.currentTimeMillis() + 60_000))
                .signWith(KEY_PAIR.getPrivate(), SignatureAlgorithm.RS256).compact();
        mockMvc.perform(get("/api/admin/employees").header("Authorization", "Bearer " + token))
                .andExpect(status().isForbidden())
                .andExpect(jsonPath("$.code").value("FORBIDDEN"));
    }

    @Test
    void delegationCanReadOnlyItsOwnBalanceAndAttendance() throws Exception {
        given(leaveService.getLeaveBalance(employee.getUsername()))
                .willReturn(LeaveBalance.builder().casualLeave(2).sickLeave(3).earnedLeave(4).build());
        given(attendanceService.getAttendanceAnalytics(employee.getUsername()))
                .willReturn(new AttendanceAnalyticsResponse(95.0, 19, 0, 0, 1, 20));
        String token = delegationToken(ISSUER, AUDIENCE, EMPLOYEE_ID, "delegation", KEY_PAIR);
        mockMvc.perform(get("/api/leaves/balance").header("Authorization", "Bearer " + token))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.casualLeave").value(2));
        mockMvc.perform(get("/api/attendance/analytics").header("Authorization", "Bearer " + token))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.totalDays").value(20));
    }

    @Test
    void selfServiceParametersCannotChangeTheAuthenticatedEmployee() throws Exception {
        given(leaveService.getMyLeaves(employee.getUsername())).willReturn(List.of());
        given(attendanceService.getMyAttendance(employee.getUsername())).willReturn(List.of());
        given(leaveService.getLeaveBalance(employee.getUsername()))
                .willReturn(LeaveBalance.builder().casualLeave(2).sickLeave(3).earnedLeave(4).build());
        given(attendanceService.getAttendanceAnalytics(employee.getUsername()))
                .willReturn(new AttendanceAnalyticsResponse(95.0, 19, 0, 0, 1, 20));
        String token = delegationToken(ISSUER, AUDIENCE, EMPLOYEE_ID, "delegation", KEY_PAIR);
        String query = "?employeeId=EMP-OTHER&userId=99&username=other";

        mockMvc.perform(get("/api/employees/me" + query).header("Authorization", "Bearer " + token))
                .andExpect(status().isOk()).andExpect(jsonPath("$.employeeId").value(EMPLOYEE_ID));
        mockMvc.perform(get("/api/leaves/my" + query).header("Authorization", "Bearer " + token)).andExpect(status().isOk());
        mockMvc.perform(get("/api/leaves/balance" + query).header("Authorization", "Bearer " + token)).andExpect(status().isOk());
        mockMvc.perform(get("/api/attendance/my" + query).header("Authorization", "Bearer " + token)).andExpect(status().isOk());
        mockMvc.perform(get("/api/attendance/analytics" + query).header("Authorization", "Bearer " + token)).andExpect(status().isOk());

        verify(leaveService).getMyLeaves(employee.getUsername());
        verify(leaveService).getLeaveBalance(employee.getUsername());
        verify(attendanceService).getMyAttendance(employee.getUsername());
        verify(attendanceService).getAttendanceAnalytics(employee.getUsername());
    }

    @Test
    void managerAndAdminEndpointsRequireTheirActualDatabaseRoles() throws Exception {
        User manager = user("EMP-MANAGER", "manager.test", Role.ROLE_MANAGER);
        User admin = user("EMP-ADMIN", "admin.test", Role.ROLE_ADMIN);
        given(userService.findByEmployeeId(manager.getEmployeeId())).willReturn(Optional.of(manager));
        given(userService.findByEmployeeId(admin.getEmployeeId())).willReturn(Optional.of(admin));
        given(leaveService.getPendingLeaves()).willReturn(List.of());
        given(userService.getAllUsers()).willReturn(List.of());

        mockMvc.perform(get("/api/leaves/pending").header("Authorization", "Bearer "
                        + delegationToken(ISSUER, AUDIENCE, manager.getEmployeeId(), "delegation", KEY_PAIR)))
                .andExpect(status().isOk());
        mockMvc.perform(get("/api/admin/employees").header("Authorization", "Bearer "
                        + delegationToken(ISSUER, AUDIENCE, admin.getEmployeeId(), "delegation", KEY_PAIR)))
                .andExpect(status().isOk());
        mockMvc.perform(get("/api/admin/employees").header("Authorization", "Bearer "
                        + delegationToken(ISSUER, AUDIENCE, manager.getEmployeeId(), "delegation", KEY_PAIR)))
                .andExpect(status().isForbidden());
    }

    @Test
    void unknownDelegationEmployeeIsRejected() throws Exception {
        String token = delegationToken(ISSUER, AUDIENCE, "EMP-UNKNOWN", "delegation", KEY_PAIR);
        mockMvc.perform(get("/api/employees/me").header("Authorization", "Bearer " + token))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.code").value("DELEGATION_TOKEN_INVALID"));
    }

    @Test
    void unauthenticatedRequestsReceiveStableErrors() throws Exception {
        mockMvc.perform(get("/api/employees/me").accept(MediaType.APPLICATION_JSON).header("X-Request-ID", "not-a-uuid"))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.code").value("UNAUTHENTICATED"))
                .andExpect(jsonPath("$.requestId").isNotEmpty())
                .andExpect(header().string("X-Request-ID", not("not-a-uuid")));
    }

    private static String delegationToken(String issuer, String audience, String employeeId, String tokenType, KeyPair keyPair) {
        return delegationToken(issuer, audience, employeeId, employeeId, tokenType, keyPair);
    }

    private static String delegationToken(String issuer, String audience, String subject, String employeeId, String tokenType, KeyPair keyPair) {
        var builder = Jwts.builder().setIssuer(issuer).setAudience(audience).setSubject(subject)
                .claim("token_type", tokenType).setId("test-jti")
                .setIssuedAt(new Date()).setExpiration(new Date(System.currentTimeMillis() + 60_000))
                .signWith(keyPair.getPrivate(), SignatureAlgorithm.RS256);
        if (employeeId != null) builder.claim("employee_id", employeeId);
        return builder.compact();
    }

    private static User user(String employeeId, String username, Role role) {
        return User.builder().id(42L).employeeId(employeeId).username(username).fullName("Test User")
                .email(username + "@example.invalid").designation("Tester").role(role)
                .status(UserStatus.ACTIVE).workMode(WorkMode.WFO).joiningDate(LocalDate.of(2024, 1, 1)).build();
    }

    private static String expiredDelegationToken() {
        return Jwts.builder().setIssuer(ISSUER).setAudience(AUDIENCE).setSubject(EMPLOYEE_ID)
                .claim("employee_id", EMPLOYEE_ID).claim("token_type", "delegation").setId("expired-jti")
                .setIssuedAt(new Date(System.currentTimeMillis() - 120_000)).setExpiration(new Date(System.currentTimeMillis() - 60_000))
                .signWith(KEY_PAIR.getPrivate(), SignatureAlgorithm.RS256).compact();
    }

    private static KeyPair keyPair() {
        try {
            KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
            generator.initialize(2048);
            return generator.generateKeyPair();
        } catch (Exception exception) {
            throw new IllegalStateException(exception);
        }
    }

    private static String publicKeyPem() {
        return "-----BEGIN PUBLIC KEY-----\n"
                + Base64.getMimeEncoder(64, "\n".getBytes()).encodeToString(KEY_PAIR.getPublic().getEncoded())
                + "\n-----END PUBLIC KEY-----";
    }
}
