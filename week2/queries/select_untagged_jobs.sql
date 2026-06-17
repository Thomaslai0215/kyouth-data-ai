SELECT source_id, description
FROM jobs
WHERE tech_stack IS NULL OR TRIM(tech_stack) = ''
ORDER BY source_id
