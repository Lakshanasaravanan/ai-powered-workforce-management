package com.slams.service;

import com.slams.dto.RegisterRequest;
import com.slams.model.*;
import com.slams.repository.DepartmentRepository;
import com.slams.repository.LeaveBalanceRepository;
import com.slams.repository.ShiftRepository;
import com.slams.repository.UserRepository;
import jakarta.annotation.PostConstruct;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDate;
import java.time.LocalTime;
import java.util.List;
import java.util.Optional;

@Service
@Transactional
public class UserService implements UserDetailsService {

    @Autowired
    private UserRepository userRepository;

    @Autowired
    private LeaveBalanceRepository leaveBalanceRepository;

    @Autowired
    private ShiftRepository shiftRepository;

    @Autowired
    private DepartmentRepository departmentRepository;

    @Autowired
    private PasswordEncoder passwordEncoder;

    // =========================================================
    // Registration
    // =========================================================

    public User registerUser(RegisterRequest request) {
        if (userRepository.existsByUsername(request.getUsername())) {
            throw new RuntimeException("Username already exists");
        }

        if (userRepository.existsByEmail(request.getEmail())) {
            throw new RuntimeException("Email already exists");
        }

        User user = User.builder()
                .username(request.getUsername())
                .password(passwordEncoder.encode(request.getPassword()))
                .email(request.getEmail())
                .fullName(request.getFullName())
                .role(request.getRole())
                .employeeId(generateEmployeeId(request.getRole()))
                .status(UserStatus.ACTIVE)
                .workMode(WorkMode.WFO)
                .joiningDate(LocalDate.now())
                .build();

        User savedUser = userRepository.save(user);

        if (savedUser.getRole() == Role.ROLE_EMPLOYEE) {
            createDefaultLeaveBalance(savedUser);
        }

        return savedUser;
    }

    // =========================================================
    // Basic Fetch APIs
    // =========================================================

    @Transactional(readOnly = true)
    public List<User> getAllUsers() {
        return userRepository.findAll();
    }

    @Transactional(readOnly = true)
    public List<User> getEmployees() {
        return userRepository.findByRole(Role.ROLE_EMPLOYEE);
    }

    @Transactional(readOnly = true)
    public List<User> getManagers() {
        return userRepository.findByRole(Role.ROLE_MANAGER);
    }

    @Transactional(readOnly = true)
    public List<User> getActiveEmployees() {
        return userRepository.findByStatusIn(
                List.of(UserStatus.ACTIVE, UserStatus.PROBATION, UserStatus.NOTICE_PERIOD)
        );
    }

    @Transactional(readOnly = true)
    public List<User> getEmployeesByManager(Long managerId) {
        User manager = userRepository.findById(managerId)
                .orElseThrow(() -> new RuntimeException("Manager not found with id: " + managerId));

        return userRepository.findByReportingManagerAndRole(manager, Role.ROLE_EMPLOYEE);
    }

    @Transactional(readOnly = true)
    public List<User> getEmployeesByDepartment(Long departmentId) {
        return userRepository.findByDepartmentId(departmentId);
    }

    @Transactional(readOnly = true)
    public Optional<User> findByUsername(String username) {
        return userRepository.findByUsername(username);
    }

    @Transactional(readOnly = true)
    public Optional<User> findById(Long id) {
        return userRepository.findById(id);
    }

    // =========================================================
    // Admin Employee Management APIs
    // =========================================================

    public User createUser(
            String username,
            String password,
            String email,
            String fullName,
            Role role,
            String employeeId,
            String designation,
            String phoneNumber,
            LocalDate joiningDate,
            Long departmentId,
            Long reportingManagerId,
            Long shiftId,
            WorkMode workMode,
            UserStatus status
    ) {
        if (userRepository.existsByUsername(username)) {
            throw new RuntimeException("Username already exists");
        }

        if (userRepository.existsByEmail(email)) {
            throw new RuntimeException("Email already exists");
        }

        if (employeeId != null && !employeeId.isBlank() && userRepository.existsByEmployeeId(employeeId)) {
            throw new RuntimeException("Employee ID already exists");
        }

        Department department = null;
        if (departmentId != null) {
            department = departmentRepository.findById(departmentId)
                    .orElseThrow(() -> new RuntimeException("Department not found with id: " + departmentId));
        }

        User reportingManager = null;
        if (reportingManagerId != null) {
            reportingManager = userRepository.findById(reportingManagerId)
                    .orElseThrow(() -> new RuntimeException("Reporting manager not found with id: " + reportingManagerId));
        }

        Shift shift = null;
        if (shiftId != null) {
            shift = shiftRepository.findById(shiftId)
                    .orElseThrow(() -> new RuntimeException("Shift not found with id: " + shiftId));
        }

        String finalEmployeeId = (employeeId == null || employeeId.isBlank())
                ? generateEmployeeId(role)
                : employeeId;

        User user = User.builder()
                .username(username)
                .password(passwordEncoder.encode(password))
                .email(email)
                .fullName(fullName)
                .employeeId(finalEmployeeId)
                .designation(designation)
                .phoneNumber(phoneNumber)
                .joiningDate(joiningDate != null ? joiningDate : LocalDate.now())
                .role(role)
                .status(status != null ? status : UserStatus.ACTIVE)
                .workMode(workMode != null ? workMode : WorkMode.WFO)
                .department(department)
                .reportingManager(reportingManager)
                .shift(shift)
                .build();

        User savedUser = userRepository.save(user);

        if (savedUser.getRole() == Role.ROLE_EMPLOYEE) {
            createDefaultLeaveBalance(savedUser);
        }

        return savedUser;
    }

    public User updateUser(
            Long userId,
            String username,
            String password,
            String email,
            String fullName,
            Role role,
            String employeeId,
            String designation,
            String phoneNumber,
            LocalDate joiningDate,
            Long departmentId,
            Long reportingManagerId,
            Long shiftId,
            WorkMode workMode,
            UserStatus status
    ) {
        User user = userRepository.findById(userId)
                .orElseThrow(() -> new RuntimeException("User not found with id: " + userId));

        if (username != null && !username.equals(user.getUsername()) && userRepository.existsByUsername(username)) {
            throw new RuntimeException("Username already exists");
        }

        if (email != null && !email.equals(user.getEmail()) && userRepository.existsByEmail(email)) {
            throw new RuntimeException("Email already exists");
        }

        if (employeeId != null && !employeeId.isBlank()
                && !employeeId.equals(user.getEmployeeId())
                && userRepository.existsByEmployeeId(employeeId)) {
            throw new RuntimeException("Employee ID already exists");
        }

        Department department = null;
        if (departmentId != null) {
            department = departmentRepository.findById(departmentId)
                    .orElseThrow(() -> new RuntimeException("Department not found with id: " + departmentId));
        }

        User reportingManager = null;
        if (reportingManagerId != null) {
            reportingManager = userRepository.findById(reportingManagerId)
                    .orElseThrow(() -> new RuntimeException("Reporting manager not found with id: " + reportingManagerId));
        }

        Shift shift = null;
        if (shiftId != null) {
            shift = shiftRepository.findById(shiftId)
                    .orElseThrow(() -> new RuntimeException("Shift not found with id: " + shiftId));
        }

        if (username != null && !username.isBlank()) {
            user.setUsername(username);
        }
        if (email != null && !email.isBlank()) {
            user.setEmail(email);
        }
        if (fullName != null && !fullName.isBlank()) {
            user.setFullName(fullName);
        }
        if (employeeId != null && !employeeId.isBlank()) {
            user.setEmployeeId(employeeId);
        }
        if (designation != null) {
            user.setDesignation(designation);
        }
        if (phoneNumber != null) {
            user.setPhoneNumber(phoneNumber);
        }
        if (joiningDate != null) {
            user.setJoiningDate(joiningDate);
        }
        if (role != null) {
            user.setRole(role);
        }
        if (status != null) {
            user.setStatus(status);
        }
        if (workMode != null) {
            user.setWorkMode(workMode);
        }

        user.setDepartment(department);
        user.setReportingManager(reportingManager);
        user.setShift(shift);

        if (password != null && !password.isBlank()) {
            user.setPassword(passwordEncoder.encode(password));
        }

        return userRepository.save(user);
    }

    public User deactivateUser(Long userId) {
        User user = userRepository.findById(userId)
                .orElseThrow(() -> new RuntimeException("User not found with id: " + userId));

        user.setStatus(UserStatus.TERMINATED);
        return userRepository.save(user);
    }

    public User reactivateUser(Long userId) {
        User user = userRepository.findById(userId)
                .orElseThrow(() -> new RuntimeException("User not found with id: " + userId));

        user.setStatus(UserStatus.ACTIVE);
        return userRepository.save(user);
    }

    // =========================================================
    // Seed Data
    // =========================================================

    @PostConstruct
    @Transactional
    public void seedInitialData() {
        if (userRepository.count() > 0) {
            return;
        }

        // 1. Seed Shift
        Shift generalShift = Shift.builder()
                .name("General Shift")
                .startTime(LocalTime.of(9, 0))
                .endTime(LocalTime.of(18, 0))
                .gracePeriodMinutes(15)
                .build();
        shiftRepository.save(generalShift);

        // 2. Seed Admin
        User admin = User.builder()
                .username("admin")
                .password(passwordEncoder.encode("admin123"))
                .email("admin@slams.com")
                .fullName("System Administrator")
                .role(Role.ROLE_ADMIN)
                .employeeId("ADM-001")
                .designation("System Administrator")
                .joiningDate(LocalDate.now())
                .shift(generalShift)
                .status(UserStatus.ACTIVE)
                .workMode(WorkMode.WFO)
                .build();
        admin = userRepository.save(admin);

        // 3. Seed Department
        Department engineering = Department.builder()
                .code("ENG")
                .name("Engineering")
                .description("Software Development and QA")
                .manager(admin)
                .active(true)
                .build();
        engineering = departmentRepository.save(engineering);

        // 4. Seed Manager
        User manager = User.builder()
                .username("manager")
                .password(passwordEncoder.encode("manager123"))
                .email("manager@slams.com")
                .fullName("Sarah Jenkins")
                .role(Role.ROLE_MANAGER)
                .employeeId("MGR-001")
                .designation("Engineering Manager")
                .joiningDate(LocalDate.now())
                .department(engineering)
                .shift(generalShift)
                .status(UserStatus.ACTIVE)
                .workMode(WorkMode.WFO)
                .build();
        manager = userRepository.save(manager);

        engineering.setManager(manager);
        departmentRepository.save(engineering);

        // 5. Seed Employees
        User john = User.builder()
                .username("john")
                .password(passwordEncoder.encode("123"))
                .email("john@slams.com")
                .fullName("John Doe")
                .role(Role.ROLE_EMPLOYEE)
                .employeeId("EMP-001")
                .designation("Software Engineer")
                .joiningDate(LocalDate.now())
                .department(engineering)
                .reportingManager(manager)
                .shift(generalShift)
                .status(UserStatus.ACTIVE)
                .workMode(WorkMode.WFO)
                .build();
        john = userRepository.save(john);

        User alice = User.builder()
                .username("alice")
                .password(passwordEncoder.encode("123"))
                .email("alice@slams.com")
                .fullName("Alice Smith")
                .role(Role.ROLE_EMPLOYEE)
                .employeeId("EMP-002")
                .designation("QA Analyst")
                .joiningDate(LocalDate.now())
                .department(engineering)
                .reportingManager(manager)
                .shift(generalShift)
                .status(UserStatus.ACTIVE)
                .workMode(WorkMode.WFO)
                .build();
        alice = userRepository.save(alice);

        User kavin = User.builder()
                .username("kavin")
                .password(passwordEncoder.encode("123"))
                .email("kavin@slams.com")
                .fullName("Kavin Raj")
                .role(Role.ROLE_EMPLOYEE)
                .employeeId("EMP-003")
                .designation("Backend Developer")
                .joiningDate(LocalDate.now())
                .department(engineering)
                .reportingManager(manager)
                .shift(generalShift)
                .status(UserStatus.ACTIVE)
                .workMode(WorkMode.HYBRID)
                .build();
        kavin = userRepository.save(kavin);

        User priya = User.builder()
                .username("priya")
                .password(passwordEncoder.encode("123"))
                .email("priya@slams.com")
                .fullName("Priya Nair")
                .role(Role.ROLE_EMPLOYEE)
                .employeeId("EMP-004")
                .designation("Frontend Developer")
                .joiningDate(LocalDate.now())
                .department(engineering)
                .reportingManager(manager)
                .shift(generalShift)
                .status(UserStatus.ACTIVE)
                .workMode(WorkMode.WFH)
                .build();
        priya = userRepository.save(priya);

        // 6. Seed Leave Balances
        createDefaultLeaveBalance(john);
        createDefaultLeaveBalance(alice);
        createDefaultLeaveBalance(kavin);
        createDefaultLeaveBalance(priya);
    }

    // =========================================================
    // Helpers
    // =========================================================

    private void createDefaultLeaveBalance(User user) {
        boolean alreadyExists = leaveBalanceRepository.findByUserId(user.getId()).isPresent();
        if (!alreadyExists) {
            LeaveBalance balance = LeaveBalance.builder()
                    .user(user)
                    .casualLeave(12)
                    .sickLeave(15)
                    .earnedLeave(18)
                    .build();
            leaveBalanceRepository.save(balance);
        }
    }

    private String generateEmployeeId(Role role) {
        String prefix = switch (role) {
            case ROLE_ADMIN -> "ADM";
            case ROLE_MANAGER -> "MGR";
            case ROLE_EMPLOYEE -> "EMP";
        };
        return prefix + "-" + System.currentTimeMillis();
    }

    // =========================================================
    // Spring Security
    // =========================================================

    @Override
    @Transactional(readOnly = true)
    public UserDetails loadUserByUsername(String username) throws UsernameNotFoundException {
        return userRepository.findByUsername(username)
                .orElseThrow(() -> new UsernameNotFoundException("User not found: " + username));
    }
}