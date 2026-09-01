ALTER TABLE wukong_telegram_notification_outbox
    ADD COLUMN message_id INTEGER NOT NULL DEFAULT 0;
