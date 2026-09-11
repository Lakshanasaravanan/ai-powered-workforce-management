package com.slams.service;

import com.slams.model.FaceEmbedding;
import com.slams.model.User;
import com.slams.repository.FaceEmbeddingRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.multipart.MultipartFile;

import java.time.LocalDateTime;

@Service
@RequiredArgsConstructor
public class FaceRecognitionService {

    private static final String MODEL_VERSION = "face-recognition-v1";

    private final FaceEmbeddingRepository faceEmbeddingRepository;
    private final UserService userService;
    private final FaceRecognitionClient faceRecognitionClient;

    @Transactional
    public FaceEmbedding enrollFace(String username, MultipartFile file) {

        User user = userService.findByUsername(username)
                .orElseThrow(() ->
                        new RuntimeException("User not found: " + username)
                );

        FaceRecognitionClient.FaceEmbeddingResult result =
                faceRecognitionClient.generateEmbedding(file);

        if (result == null
                || result.embedding() == null
                || result.dimension() != 128) {

            throw new RuntimeException(
                    "Invalid face embedding received from face recognition service"
            );
        }

        faceEmbeddingRepository
                .findByUserIdAndActiveTrue(user.getId())
                .forEach(existing -> {
                    existing.setActive(false);
                    faceEmbeddingRepository.save(existing);
                });

        FaceEmbedding faceEmbedding = FaceEmbedding.builder()
                .user(user)
                .embeddingVector(result.embedding().toString())
                .modelVersion(MODEL_VERSION)
                .enrolledAt(LocalDateTime.now())
                .active(true)
                .build();

        return faceEmbeddingRepository.save(faceEmbedding);
    }
}