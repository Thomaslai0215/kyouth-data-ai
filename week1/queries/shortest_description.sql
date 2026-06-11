SELECT LENGTH(description) AS desc_len, source_id, job_title
FROM jobs
WHERE description IS NOT NULL
ORDER BY desc_len ASC
LIMIT 1
