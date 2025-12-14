import base64
import json
import logging
import os

# Configure logging
logging.basicConfig(level=logging.INFO)

# Placeholder for a more sophisticated alert processor.
# In a real system, this might dispatch to different systems (PagerDuty, Slack, etc.)
class AlertProcessor:
    def __init__(self):
        pass

    def process_critical_alert(self, log_entry: dict):
        severity = log_entry.get('severity', 'UNKNOWN')
        message = log_entry.get('textPayload') or log_entry.get('jsonPayload', {})
        resource_type = log_entry.get('resource', {}).get('type', 'unknown')
        
        logging.info(f"ALERT: Critical log detected ({severity}) from {resource_type}: {message}")
        # In a real implementation, this would trigger external alerts
        # Example: send_slack_notification(message)
        # Example: create_pagerduty_incident(message)

alert_processor = AlertProcessor()

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
            
            # Logic: If CRITICAL, maybe send a Slack notification or specific Alert
            if severity == 'CRITICAL' or severity == 'ALERT':
                alert_processor.process_critical_alert(log_entry)
            
            logging.info(f"Processed log: {severity} from {log_entry.get('resource', {}).get('type', 'unknown')}")

    except Exception as e:
        logging.error(f"Error processing log: {e}")