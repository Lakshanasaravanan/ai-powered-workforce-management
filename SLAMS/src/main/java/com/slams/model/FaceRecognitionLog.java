package com.slams.model;

import jakarta.persistence.*;
import lombok.*;

import java.time.LocalDateTime;

@Entity
@Table(name = "face_recognition_log")
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class FaceRecognitionLog {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    /**
     * User identified during the recognition attempt.
     * Can be null when the face is unknown.
     */
    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "attempted_user_id")
    private User attemptedUser;

    /**
     * Whether the recognition attempt successfully matched
     * an enrolled employee.
     */
    @Column(nullable = false)
    private boolean matched;

    /**
     * Recognition confidence/distance converted into
     * the application's confidence representation.
     */
    private Double confidenceScore;

    /**
     * CHECK_IN or CHECK_OUT.
     */
    @Column(length = 20)
    private String action;

    /**
     * Device/kiosk identifier from which the attempt originated.
     */
    @Column(length = 100)
    private String deviceId;

    /**
     * Time of the recognition attempt.
     */
    @Column(nullable = false)
    private LocalDateTime createdAt;
}