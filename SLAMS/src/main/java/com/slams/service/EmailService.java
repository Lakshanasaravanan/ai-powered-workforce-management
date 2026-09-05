package com.slams.service;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

@Service
public class EmailService {

    private static final Logger logger = LoggerFactory.getLogger(EmailService.class);

    public void sendEmail(String to, String subject, String body) {
        logger.info("\n--------------------------------------------------" +
                    "\n[EMAIL SIMULATION] Dispatching Notification..." +
                    "\nRecipient: " + to +
                    "\nSubject:   " + subject +
                    "\nMessage:   " + body +
                    "\n--------------------------------------------------");
    }
}
