import base64
import json
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)

def process_log_entry(event, context):
    """Triggered from a message on a Cloud Pub/Sub topic.
    Args:
         event (dict): Event payload.
         context (google.cloud.functions.Context): Metadata for the event.
    """
    try:
        if 'data' in event:
            pubsub_message = base64.b64decode(event['data']).decode('utf-8')
            log_entry = json.loads(pubsub_message)
            
            # Extract key info
            severity = log_entry.get('severity', 'UNKNOWN')
            resource = log_entry.get('resource', {})
            text_payload = log_entry.get('textPayload', '')
            json_payload = log_entry.get('jsonPayload', {})
            
            # Logic: If CRITICAL, maybe send a Slack notification or specific Alert
            if severity == 'CRITICAL' or severity == 'ALERT':
                logging.info(f"CRITICAL LOG DETECTED: {text_payload or json_payload}")
                # TODO: Implement Slack/PagerDuty Webhook here
            
            logging.info(f"Processed log: {severity} from {resource.get('type', 'unknown')}")

    except Exception as e:
        logging.error(f"Error processing log: {e}")
