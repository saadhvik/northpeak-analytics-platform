{#
    Normalize a TIMESTAMP WITH TIME ZONE column to a naive UTC TIMESTAMP.

    Why: the raw TheLook load types some timestamp columns as TIMESTAMPTZ and
    others as naive TIMESTAMP, even though every value is stored in UTC (+00:00).
    Mixing the two blows up downstream date math and joins. Every staging model
    routes tz-aware columns through this macro so the whole warehouse speaks one
    timestamp type: naive TIMESTAMP, in UTC.

    `<tstz> AT TIME ZONE 'UTC'` yields the UTC wall-clock as a naive TIMESTAMP
    in DuckDB. Naive columns that are already UTC are cast with ::timestamp
    directly in the model (no tz interpretation needed).
#}
{% macro to_utc(column_name) %}
    (cast({{ column_name }} as timestamptz) at time zone 'UTC')::timestamp
{% endmacro %}
