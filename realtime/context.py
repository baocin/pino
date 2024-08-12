from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates
from datetime import datetime, timedelta, timezone
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

async def get_current_context_logic(request: Request, json_only: bool = False, hours_ago: int = 24):
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
            (SELECT ST_Distance(d.location::geography, ST_GeogFromText(ST_AsText(kl.gps_polygon)))
             FROM location_transitions ltl
             JOIN known_locations kl ON ltl.location_id = kl.id
             WHERE ltl.device_id = d.id
             ORDER BY ltl.created_at DESC
             LIMIT 1) AS distance_from_last_known_location,
            CASE 
                WHEN d.speed IS NULL THEN 'unknown'
                WHEN d.speed <= 0 THEN 'stationary'
                WHEN d.speed <= 3 THEN 'walking'
                WHEN d.speed <= 10 THEN 'running'
                WHEN d.speed <= 1000 THEN 'vehicle'
                WHEN d.speed > 1000 THEN 'aircraft'
                ELSE 'unknown'
            END AS movement_type,
            ABS(EXTRACT(EPOCH FROM (now() AT TIME ZONE 'UTC' - d.last_movement AT TIME ZONE 'UTC'))) / 60 AS minutes_since_last_movement,
            d.last_known_address::json->>'street' AS street,
            d.last_known_address::json->>'city' AS city,
            d.last_known_address::json->>'country' AS country,
            (SELECT COUNT(*) FROM location_transitions lt WHERE lt.device_id = d.id AND lt.created_at > now() - interval '24 hours') AS location_changes_last_24h,
            (SELECT STRING_AGG(DISTINCT kl.name, ', ') 
             FROM location_transitions lt 
             JOIN known_locations kl ON lt.location_id = kl.id
             WHERE lt.device_id = d.id AND lt.created_at > now() - interval '24 hours') AS visited_known_locations_last_24h,
            (SELECT COUNT(*) FROM emails e WHERE e.date_received > now() - interval '24 hours') AS emails_received_last_24h,
            (SELECT COUNT(*) FROM calendar_events ce 
             WHERE ce.start_time > now() 
               AND ce.start_time < now() + interval '24 hours'
               AND ce.summary NOT ILIKE '%Forecast%'
               AND ce.summary NOT ILIKE '%work%') AS upcoming_events_next_24h,
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
             LIMIT 5) AS relevant_calendar_event_based_on_time,
            (SELECT EXTRACT(EPOCH FROM (now() - MAX(gps.created_at))) / 3600
             FROM gps_data gps
             WHERE gps.device_id = d.id
               AND ST_DistanceSphere(
                   ST_MakePoint(gps.longitude, gps.latitude),
                   d.location::geometry
               ) > 76.2  -- 250 feet in meters
               AND gps.created_at > now() - interval '168 hours') AS hours_at_current_location
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
            'relevant_calendar_event_based_on_time': result[0][21],
            'hours_at_current_location': f"{round(float(result[0][22]), 1)} hours" if result[0][22] is not None else None
        }

        # Define the time range for context
        time_range = timedelta(hours=hours_ago)  # Default to 1 day
        
        # New queries
        speech_query = """
        WITH speech_intervals AS (
            SELECT 
                text, 
                created_at,
                LAG(created_at) OVER (ORDER BY created_at) AS prev_created_at
            FROM speech_data
            WHERE created_at > NOW() - INTERVAL %s
        ),
        merged_speech AS (
            SELECT 
                STRING_AGG(text, ' ') AS text,
                MIN(created_at) AS start_time,
                MAX(created_at) AS end_time
            FROM (
                SELECT 
                    text,
                    created_at,
                    SUM(CASE 
                        WHEN prev_created_at IS NULL OR EXTRACT(EPOCH FROM (created_at - prev_created_at)) > 60 
                        THEN 1 
                        ELSE 0 
                    END) OVER (ORDER BY created_at) AS speech_group
                FROM speech_intervals
            ) grouped_speech
            GROUP BY speech_group
        )
        SELECT text, start_time AS created_at
        FROM merged_speech
        ORDER BY start_time DESC;
        """
        
        ocr_query = """
        SELECT ocr_result, created_at
        FROM image_data
        WHERE created_at > NOW() - INTERVAL %s
        AND ocr_result IS NOT NULL
        ORDER BY created_at DESC;
        """
        location_query = """
        SELECT DISTINCT ON (dsl.device_id) 
            dsl.device_id,
            kl.name AS location_name,
            dsl.timestamp
        FROM device_status_log dsl
        JOIN known_locations kl ON ST_Contains(kl.gps_polygon, ST_SetSRID(ST_Point(ST_X(dsl.location::geometry), ST_Y(dsl.location::geometry)), 4326))
        WHERE dsl.timestamp > NOW() - INTERVAL %s
        ORDER BY dsl.device_id, dsl.timestamp DESC;
        """
        known_class_query = """
        SELECT kc.name, kcd.created_at
        FROM known_class_detections kcd
        JOIN known_classes kc ON kcd.known_class_id = kc.id
        WHERE kcd.created_at > NOW() - INTERVAL %s
        ORDER BY kcd.created_at DESC;
        """
        all_known_classes_query = """
        SELECT 
            kc.name, 
            MAX(kcd.created_at) AS last_detected,
            EXTRACT(EPOCH FROM (now() - MAX(kcd.created_at))) / 3600 AS hours_since_last_detected
        FROM known_class_detections kcd
        JOIN known_classes kc ON kcd.known_class_id = kc.id
        GROUP BY kc.name;
        """
        
        llm_actions_query = """
        SELECT id, created_at, metadata, success
        FROM public.llm_actions
        WHERE created_at > NOW() - INTERVAL %s
        ORDER BY created_at DESC;
        """

        llm_memories_query = """
        SELECT id, created_at, content, metadata
        FROM public.llm_memories
        WHERE created_at > NOW() - INTERVAL %s
        ORDER BY created_at DESC;
        """

        tweets_query = """
        SELECT id, "timestamp", tweet_text as text
        FROM public.tweets
        WHERE "timestamp" > NOW() - INTERVAL %s
        ORDER BY "timestamp" DESC;
        """

        github_repos_query = """
        SELECT repo_id, created_at, repo_name
        FROM public.github_stars
        WHERE created_at > NOW() - INTERVAL %s
        ORDER BY created_at DESC;
        """

        contacts_query = """
        SELECT id, created_at, full_name as name, email, phone
        FROM public.contacts
        WHERE created_at > NOW() - INTERVAL %s
        ORDER BY created_at DESC;
        """

        documents_query = """
        SELECT id, created_at, name, document_text
        FROM public.documents
        ORDER BY created_at DESC;
        """
        
        # Execute new queries
        speech_data = db.sync_query(speech_query, (time_range,)) if speech_query else None
        ocr_data = db.sync_query(ocr_query, (time_range,)) if ocr_query else None
        location_data = db.sync_query(location_query, (time_range,)) if location_query else None
        known_class_data = db.sync_query(known_class_query, (time_range,)) if known_class_query else None
        all_known_classes_data = db.sync_query(all_known_classes_query) if all_known_classes_query else None
        llm_actions_data = db.sync_query(llm_actions_query, (time_range,)) if llm_actions_query else None
        llm_memories_data = db.sync_query(llm_memories_query, (time_range,)) if llm_memories_query else None
        tweets_data = db.sync_query(tweets_query, (time_range,)) if tweets_query else None
        github_repos_data = db.sync_query(github_repos_query, (time_range,)) if github_repos_query else None
        contacts_data = db.sync_query(contacts_query, (time_range,)) if contacts_query else None
        documents_data = db.sync_query(documents_query) if documents_query else None

        # Merge timeline data
        timeline_data = []
        if speech_data:
            for row in speech_data:
                if row and len(row) >= 2:
                    timeline_data.append({'type': 'speech', 'text': row[0], 'timestamp': row[1]})
        if ocr_data:
            for row in ocr_data:
                if row and len(row) >= 2:
                    timeline_data.append({'type': 'ocr', 'text': row[0], 'timestamp': row[1]})
        if location_data:
            for row in location_data:
                if row and len(row) >= 3:
                    timeline_data.append({'type': 'location', 'text': row[1], 'timestamp': row[2]})
        if known_class_data:
            for row in known_class_data:
                if row and len(row) >= 2:
                    timeline_data.append({'type': 'known_class', 'text': row[0], 'timestamp': row[1]})
        if tweets_data:
            for row in tweets_data:
                if row and len(row) >= 3:
                    timeline_data.append({'type': 'tweet', 'id': row[0], 'text': row[2], 'timestamp': row[1]})
        if github_repos_data:
            for row in github_repos_data:
                if row and len(row) >= 3:
                    timeline_data.append({'type': 'github_repo', 'id': row[0], 'full_name': row[2], 'timestamp': row[1]})
        if contacts_data:
            for row in contacts_data:
                if row and len(row) >= 5:
                    timeline_data.append({'type': 'contact', 'id': row[0], 'name': row[2], 'email': row[3], 'phone': row[4], 'timestamp': row[1]})
        
        # Sort timeline data by timestamp
        if timeline_data:
            timeline_data.sort(key=lambda x: x.get('timestamp', datetime.min), reverse=True)

        context['timeline_data'] = timeline_data

        # TODO: Placeholder until I find a good way to get 'active device id' from the request
        context['active_device_id'] = 1

        # TODO: pull from database
        last_llm_call = datetime.now(timezone.utc) - timedelta(minutes=1)
        time_since_last_call = datetime.now(timezone.utc) - last_llm_call
        minutes = int(time_since_last_call.total_seconds() / 60)
        context['last_time_llm_was_called_relative'] = f"{minutes} minutes ago"


        last_sent_notification_hours_ago = None
        try:
            last_sent_at_row = db.sync_query(
                """
                SELECT sent_at AT TIME ZONE 'UTC' FROM gotify_message_log 
                ORDER BY sent_at DESC 
                LIMIT 1
                """
            )

            if last_sent_at_row:
                last_sent_at = last_sent_at_row[0][0]
                time_since_last_sent = datetime.utcnow() - last_sent_at
                logger.info(f"context - Time since last sent: {time_since_last_sent}")
                last_sent_notification_hours_ago = time_since_last_sent.total_seconds() / 3600
                context['last_sent_notification_hours_ago'] = f"{last_sent_notification_hours_ago:.2f} hours ago"
                logger.info(f"Context: {context['last_sent_notification_hours_ago']}")
                
                
        except Exception as e:
            logger.error(f"Error querying gotify_message_log: {str(e)}")

        # Add known classes detection times to context
        known_classes_relative = {}
        if all_known_classes_data:
            for row in all_known_classes_data:
                if row and len(row) >= 3:
                    class_name = row[0]
                    hours_since_last_detected = row[2]
                    if class_name is not None:
                        if hours_since_last_detected is not None:
                            known_classes_relative[class_name] = f"{int(hours_since_last_detected)} hours ago"
                        else:
                            known_classes_relative[class_name] = None

        context['known_classes_relative'] = known_classes_relative

        # Add LLM actions to context
        context['llm_actions'] = []
        if llm_actions_data:
            for row in llm_actions_data:
                if row and len(row) >= 4:
                    context['llm_actions'].append({
                        'id': str(row[0]) if row[0] is not None else None,
                        'created_at': row[1],
                        'metadata': row[2],
                        'success': row[3]
                    })

        # Add LLM memories to context
        context['llm_memories'] = []
        if llm_memories_data:
            for row in llm_memories_data:
                if row and len(row) >= 4:
                    context['llm_memories'].append({
                        'id': str(row[0]) if row[0] is not None else None,
                        'created_at': row[1],
                        'content': row[2],
                        'metadata': row[3]
                    })

        # Add documents to context
        context['documents'] = []
        if documents_data:
            for row in documents_data:
                if row and len(row) >= 4:
                    context['documents'].append({
                        'id': str(row[0]) if row[0] is not None else None,
                        'created_at': row[1],
                        'title': row[2],
                        'content': row[3]
                    })

        if json_only:
            # Convert datetime objects to ISO format strings
            for item in context.get('timeline_data', []):
                if 'timestamp' in item and item['timestamp'] is not None:
                    item['timestamp'] = item['timestamp'].isoformat()
            
            # Convert datetime objects in known_classes_relative
            for class_name, time_ago in context.get('known_classes_relative', {}).items():
                if time_ago is not None:
                    # Extract the number of hours from the string
                    hours = int(time_ago.split()[0])
                    # Convert to a relative time string
                    context['known_classes_relative'][class_name] = f"{hours} hours ago"

            # Convert datetime objects in llm_actions, llm_memories, and documents
            for action in context.get('llm_actions', []):
                if 'created_at' in action and action['created_at'] is not None:
                    action['created_at'] = action['created_at'].isoformat()
            for memory in context.get('llm_memories', []):
                if 'created_at' in memory and memory['created_at'] is not None:
                    memory['created_at'] = memory['created_at'].isoformat()
            for document in context.get('documents', []):
                if 'created_at' in document and document['created_at'] is not None:
                    document['created_at'] = document['created_at'].isoformat()

            return JSONResponse(content=context)
        return templates.TemplateResponse("current_context.html", {"request": request, **context})
    except Exception as e:
        logger.error(f"Error fetching current context: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error fetching current context: {str(e)}")