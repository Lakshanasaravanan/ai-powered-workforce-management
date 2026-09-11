package com.slams.controller;

import com.slams.model.FaceEmbedding;
import com.slams.service.FaceRecognitionService;
import lombok.RequiredArgsConstructor;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;

import java.security.Principal;

@RestController
@RequestMapping("/api/face")
@RequiredArgsConstructor
public class FaceRecognitionController {

    private final FaceRecognitionService faceRecognitionService;

    @PostMapping(
            value = "/enroll",
            consumes = MediaType.MULTIPART_FORM_DATA_VALUE
    )
    @PreAuthorize("hasAnyRole('EMPLOYEE', 'HR', 'ADMIN')")
    public ResponseEntity<?> enrollFace(
            Principal principal,
            @RequestPart("file") MultipartFile file) {

        try {
            if (file == null || file.isEmpty()) {
                return ResponseEntity
                        .badRequest()
                        .body("Please provide an image.");
            }

            FaceEmbedding embedding =
                    faceRecognitionService.enrollFace(
                            principal.getName(),
                            file
                    );

            return ResponseEntity.ok(
                    "Face enrolled successfully for "
                            + principal.getName()
            );

        } catch (Exception e) {
            return ResponseEntity
                    .badRequest()
                    .body(e.getMessage());
        }
    }
}