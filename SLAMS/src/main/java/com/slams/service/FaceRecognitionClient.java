package com.slams.service;

import lombok.RequiredArgsConstructor;
import org.springframework.http.MediaType;
import org.springframework.http.client.MultipartBodyBuilder;
import org.springframework.stereotype.Service;
import org.springframework.util.MultiValueMap;
import org.springframework.web.client.RestClient;
import org.springframework.web.multipart.MultipartFile;

import java.util.List;

@Service
@RequiredArgsConstructor
public class FaceRecognitionClient {

    private final RestClient faceRecognitionRestClient;

    public FaceEmbeddingResult generateEmbedding(MultipartFile file) {

        MultipartBodyBuilder builder = new MultipartBodyBuilder();

        builder.part("file", file.getResource())
                .filename(file.getOriginalFilename())
                .contentType(
                        file.getContentType() != null
                                ? MediaType.parseMediaType(file.getContentType())
                                : MediaType.IMAGE_JPEG
                );

        MultiValueMap<String, org.springframework.http.HttpEntity<?>> body =
                builder.build();

        return faceRecognitionRestClient.post()
                .uri("/face/embedding")
                .contentType(MediaType.MULTIPART_FORM_DATA)
                .body(body)
                .retrieve()
                .body(FaceEmbeddingResult.class);
    }

    public record FaceEmbeddingResult(
            List<Double> embedding,
            int dimension
    ) {
    }
}