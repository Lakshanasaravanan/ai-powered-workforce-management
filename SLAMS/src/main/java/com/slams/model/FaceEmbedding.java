package com.slams.model;

import jakarta.persistence.*;
import lombok.*;

import java.time.LocalDateTime;

@Entity
@Table(name = "face_embedding")
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class FaceEmbedding {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    /**
     * Employee/User to whom this face embedding belongs.
     */
    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "user_id", nullable = false)
    private User user;

    /**
     * Face embedding stored as a JSON string.
     * face_recognition produces a 128-dimensional vector.
     */
    @Lob
    @Column(name = "embedding_vector", nullable = false, columnDefinition = "TEXT")
    private String embeddingVector;

    /**
     * Version of the face recognition model used.
     */
    @Column(name = "model_version", nullable = false, length = 50)
    private String modelVersion;

    /**
     * Date and time when the face was enrolled.
     */
    @Column(name = "enrolled_at", nullable = false)
    private LocalDateTime enrolledAt;

    /**
     * Allows an administrator to deactivate an old embedding
     * without deleting the record.
     */
    @Column(name = "is_active", nullable = false)
    @Builder.Default
    private boolean active = true;
}