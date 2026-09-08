package com.slams.repository;

import com.slams.model.FaceEmbedding;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.util.List;
import java.util.Optional;

@Repository
public interface FaceEmbeddingRepository extends JpaRepository<FaceEmbedding, Long> {

    List<FaceEmbedding> findByUserIdAndActiveTrue(Long userId);

    List<FaceEmbedding> findByActiveTrue();

    Optional<FaceEmbedding> findFirstByUserIdAndActiveTrue(Long userId);
}