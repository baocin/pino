#!/bin/bash

# Load environment variables from .env file
source .env

echo $DB_NAME
# PGPASSWORD=$DB_PASSWORD pg_dump -h $DB_HOST -U $DB_USER -s $DB_NAME > schema.sql
# Simplify the schema to only keep core pieces like table, functions, views, etc.
# PGPASSWORD=$DB_PASSWORD pg_dump -h $DB_HOST -U $DB_USER -s -T 'pg_*' -T 'sql_*' -T 'information_schema' $DB_NAME > schema.sql

PGPASSWORD=$DB_PASSWORD pg_dump -h $DB_HOST -U $DB_USER -s --no-owner --no-privileges --no-comments $DB_NAME > schema_backup.sql

echo "Database schema exported to schema_backup.sql"
