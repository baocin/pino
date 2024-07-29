from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates
from datetime import datetime, timezone
import logging
import os
from libraries.db.db import DB

templates = Jinja2Templates(directory="templates")
logger = logging.getLogger(__name__)

db = DB(
    host=os.getenv("POSTGRES_HOST"),
    port=os.getenv("POSTGRES_PORT"),
    database=os.getenv("POSTGRES_DB"),
    user=os.getenv("POSTGRES_USER"),
    password=os.getenv("POSTGRES_PASSWORD")
)

async def get_current_context_logic(request: Request, json_only: bool = False):
    try:
        query = """
        SELECT 
            d.name AS device_name,
            d.speed,
            d.screen_up,
            d.last_movement,
            d.online,
            kl.name AS last_known_location,
            ST_AsText(d.location) AS current_location,
            ST_Distance(d.location::geography, kl.gps_polygon::geography) AS distance_from_last_known_location,
            CASE 
                WHEN d.speed IS NULL THEN 'unknown'
                WHEN d.speed <= 0 THEN 'stationary'
                WHEN d.speed <= 3 THEN 'walking'
                WHEN d.speed <= 10 THEN 'running'
                WHEN d.speed <= 1000 THEN 'vehicle'
                WHEN d.speed > 1000 THEN 'aircraft'
                ELSE 'unknown'
            END AS movement_type,
            EXTRACT(EPOCH FROM (now() - d.last_movement)) / 60 AS minutes_since_last_movement,
            d.last_known_address::json->>'street' AS street,
            d.last_known_address::json->>'city' AS city,
            d.last_known_address::json->>'country' AS country,
            (SELECT COUNT(*) FROM location_transitions lt WHERE lt.device_id = d.id AND lt.created_at > now() - interval '24 hours') AS location_changes_last_24h,
            (SELECT STRING_AGG(DISTINCT kl.name, ', ') 
             FROM location_transitions lt 
             JOIN known_locations kl ON lt.location_id = kl.id
             WHERE lt.device_id = d.id AND lt.created_at > now() - interval '24 hours') AS visited_known_locations_last_24h,
            (SELECT COUNT(*) FROM emails e WHERE e.date_received > now() - interval '24 hours') AS emails_received_last_24h,
            (SELECT COUNT(*) FROM calendar_events ce WHERE ce.start_time > now() AND ce.start_time < now() + interval '24 hours') AS upcoming_events_next_24h,
            (SELECT STRING_AGG(DISTINCT 
                ce.summary || ' (' || 
                CASE 
                    WHEN ce.start_time - now() < interval '1 hour' 
                    THEN EXTRACT(MINUTE FROM (ce.start_time - now())) || ' minutes'
                    ELSE EXTRACT(HOUR FROM (ce.start_time - now())) || ' hours'
                END || ')', ', ') 
             FROM calendar_events ce 
             WHERE ce.start_time > now() 
               AND ce.start_time < now() + interval '24 hours'
               AND ce.summary NOT ILIKE '%Forecast%'
               AND ce.summary NOT ILIKE '%work%') AS upcoming_event_titles,
            (SELECT MAX(kcd.created_at)
             FROM known_class_detections kcd
             JOIN known_classes kc ON kcd.known_class_id = kc.id
             WHERE kc.name = 'electric_toothbrush') AS last_brushed_teeth,
            CASE 
                WHEN (SELECT MAX(kcd.created_at)
                      FROM known_class_detections kcd
                      JOIN known_classes kc ON kcd.known_class_id = kc.id
                      WHERE kc.name = 'electric_toothbrush') > now() - interval '24 hours'
                THEN true
                ELSE false
            END AS brushed_teeth_last_24h,
            (SELECT ce.summary
             FROM calendar_events ce
             WHERE ce.related_known_location_id = d.last_known_location_id
             ORDER BY ce.start_time
             LIMIT 1) AS relevant_calendar_event_based_on_known_location,
            (SELECT STRING_AGG(ce.summary, ', ')
             FROM calendar_events ce
             WHERE ce.start_time BETWEEN now() - interval '3 hours' AND now() + interval '3 hours'
             LIMIT 5) AS relevant_calendar_event_based_on_time
        FROM
            devices d
        LEFT JOIN known_locations kl ON kl.id = d.last_known_location_id
        WHERE d.id = 1
        """
        result = db.sync_query(query)
        
        if not result or len(result) == 0:
            raise HTTPException(status_code=404, detail="No data found")
        
        context = {
            'device_name': result[0][0],
            'online': result[0][4],
            'speed': float(result[0][1]) if result[0][1] is not None else None,
            'screen_up': result[0][2],
            'last_movement': result[0][3].isoformat() if result[0][3] else None,
            'movement_type': result[0][8],
            'minutes_since_last_movement': float(result[0][9]) if result[0][9] is not None else None,
            'last_known_location': result[0][5],
            'current_location': result[0][6],
            'distance_from_last_known_location': f"{round(float(result[0][7]))} meters" if result[0][7] else None,
            'street': result[0][10],
            'city': result[0][11],
            'country': result[0][12],
            'location_changes_last_24h': int(result[0][13]) if result[0][13] is not None else 0,
            'visited_known_locations_last_24h': result[0][14],
            'emails_received_last_24h': int(result[0][15]) if result[0][15] is not None else 0,
            'upcoming_events_next_24h': int(result[0][16]) if result[0][16] is not None else 0,
            'upcoming_event_titles': result[0][17],
            'last_brushed_teeth': result[0][18].isoformat() if result[0][18] else None,
            'brushed_teeth_last_24h': result[0][19],
            'relevant_calendar_event_based_on_known_location': result[0][20],
            'last_brushed_teeth_relative': f"{int((datetime.now(timezone.utc) - result[0][18]).total_seconds() / 3600)} hours ago" if result[0][18] else None,
            'relevant_calendar_event_based_on_time': result[0][21]
        }

        if json_only:
            return JSONResponse(content=context)
        
        return templates.TemplateResponse("current_context.html", {"request": request, **context})
    
    except Exception as e:
        logger.error(f"Error fetching current context: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error fetching current context: {str(e)}")