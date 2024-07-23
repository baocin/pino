#!/bin/bash

# Load environment variables from .env file
source .env

# PGPASSWORD=$DB_PASSWORD pg_dump -h $DB_HOST -U $DB_USER -s $DB_NAME > schema.sql
# Simplify the schema to only keep core pieces like table, functions, views, etc.
PGPASSWORD=$DB_PASSWORD pg_dump -h $DB_HOST -U $DB_USER -s -T 'pg_*' -T 'sql_*' -T 'information_schema' $DB_NAME > schema.sql

echo "Database schema exported to schema.sql"
