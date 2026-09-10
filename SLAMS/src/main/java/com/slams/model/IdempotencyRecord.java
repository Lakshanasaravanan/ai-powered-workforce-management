package com.slams.model;

import jakarta.persistence.*;
import lombok.*;
import java.time.LocalDateTime;

@Entity
@Table(name = "idempotency_records", uniqueConstraints = @UniqueConstraint(name = "uk_idempotency_key", columnNames = "idempotency_key"))
@Getter @Setter @NoArgsConstructor @AllArgsConstructor @Builder
public class IdempotencyRecord {
    @Id @GeneratedValue(strategy = GenerationType.IDENTITY) private Long id;
    @Column(name = "idempotency_key", nullable = false, length = 64) private String idempotencyKey;
    @ManyToOne(fetch = FetchType.LAZY) @JoinColumn(name = "user_id", nullable = false) private User user;
    @Column(nullable = false, length = 80) private String operation;
    @Column(nullable = false, length = 64) private String payloadHash;
    @Enumerated(EnumType.STRING) @Column(nullable = false) private IdempotencyState state;
    private Integer responseStatus;
    @Column(length = 4000) private String responseBody;
    @Column(nullable = false) private LocalDateTime createdAt;
    private LocalDateTime completedAt;
}
