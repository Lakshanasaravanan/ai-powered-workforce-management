package com.slams.repository;

import com.slams.model.FaceRecognitionLog;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

@Repository
public interface FaceRecognitionLogRepository
        extends JpaRepository<FaceRecognitionLog, Long> {
}