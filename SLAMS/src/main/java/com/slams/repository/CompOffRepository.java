package com.slams.repository;

import com.slams.model.CompOff;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.util.List;

@Repository
public interface CompOffRepository extends JpaRepository<CompOff, Long> {
    List<CompOff> findByUserId(Long userId);
}
