#IoT GCP with Raspberry  3+ B Temperature on BigQUery 

#!/usr/bin/python
import board
import argparse
import time
import datetime
import uuid
import json
import jwt
import RPi.GPIO as io
import adafruit_dht
from tendo import singleton
import paho.mqtt.client as mqtt

me = singleton.SingleInstance() 

# set the following to be indicative of how you are using your heart rate sensor
rejectBPM = 45 # reject anything that is below this BPM threshold
heartbeatsToCount = 10 # number of heart beats to sample before calculating an average BPM

# Constants that shouldn't need to be changed
token_life = 60 #lifetime of the JWT token (minutes)
gpioIN = 18 #GPIO pin input on the Raspberry Pi that will receive heart rate receiver information

# end of constants

## set GPIO mode to BCM -- this takes GPIO number instead of pin number
io.setmode(io.BCM)
io.setwarnings(False)

def parse_command_line_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description=(
            'Example Google Cloud IoT Core MQTT device connection code.'))
    parser.add_argument(
            '--project_id',
            required=True,
            help='GCP cloud project name')
    parser.add_argument(
            '--registry_id', 
	    required=True, 
	    help='Cloud IoT Core registry id')
    parser.add_argument(
            '--device_id', 
	    required=True, 
	    help='Cloud IoT Core device id')
    parser.add_argument(
            '--private_key_file',
	    default='../.ssh/ec_private.pem',
            help='Path to private key file.')
    parser.add_argument(
            '--algorithm',
            choices=('RS256', 'ES256'),
            default='ES256',
            help='Which encryption algorithm to use to generate the JWT.')
    parser.add_argument(
            '--cloud_region', default='us-central1', help='GCP cloud region')
    parser.add_argument(
            '--ca_certs',
            default='../.ssh/roots.pem',
            help=('CA root from https://pki.google.com/roots.pem'))
    parser.add_argument(
            '--mqtt_bridge_hostname',
            default='mqtt.googleapis.com',
            help='MQTT bridge hostname.')
    parser.add_argument(
            '--mqtt_bridge_port',
            choices=(8883, 443),
            default=8883,
            type=int,
            help='MQTT bridge port.')
    parser.add_argument(
            '--jwt_expires_minutes',
            default=token_life,
            type=int,
            help=('Expiration time, in minutes, for JWT tokens.'))
    parser.add_argument(
            '--receiver_in',
            default=gpioIN,
	    type=int,
            help=('GPIO input pin for the heart rate sensor'))
    return parser.parse_args()


def create_jwt(cur_time, projectID, privateKeyFilepath, algorithmType):
  token = {
      'iat': cur_time,
      'exp': cur_time + datetime.timedelta(minutes=token_life),
      'aud': projectID
  }

  with open(privateKeyFilepath, 'r') as f:
    private_key = f.read()

  return jwt.encode(token, private_key, algorithm=algorithmType) # Assuming RSA, but also supports ECC

def error_str(rc):
    return '{}: {}'.format(rc, mqtt.error_string(rc))

def on_connect(unusued_client, unused_userdata, unused_flags, rc):
    print('on_connect', error_str(rc))

def on_publish(unused_client, unused_userdata, unused_mid):
    print('on_publish')

def createJSON(id, unique_id, timestamp, heartrate):
    data = {
	'sensorID' : id,
	'uniqueID' : unique_id,
	'timecollected' : timestamp,
	'temperature' : heartrate
    }

    json_str = json.dumps(data)
    return json_str

def calcBPM(startTime, endTime):   
    sampleSeconds = endTime - startTime  # calculate time gap between first and last heartbeat
    bpm = (60/sampleSeconds)*(heartbeatsToCount)
    return bpm

def main():
    args = parse_command_line_args()
    project_id = args.project_id
    gcp_location = args.cloud_region
    registry_id = args.registry_id
    device_id = args.device_id
    ssl_private_key_filepath = args.private_key_file
    ssl_algorithm = args.algorithm
    root_cert_filepath = args.ca_certs
    sensorID = registry_id + "." + device_id
    googleMQTTURL = args.mqtt_bridge_hostname
    googleMQTTPort = args.mqtt_bridge_port
    receiver_in = args.receiver_in
    
    _CLIENT_ID = 'projects/{}/locations/{}/registries/{}/devices/{}'.format(project_id, gcp_location, registry_id, device_id)
    _MQTT_TOPIC = '/devices/{}/events'.format(device_id)
	

    uniqueID = -1 # unique id if dedeplication is needed

#    io.setup(receiver_in, io.IN) # initialize receiver GPIO to the pin that will take input
    dhtDevice = adafruit_dht.DHT11(board.D3)

    print ("Ready. Waiting for signal.")

    while True:

      client = mqtt.Client(client_id=_CLIENT_ID)
      cur_time = datetime.datetime.utcnow()
      # authorization is handled purely with JWT, no user/pass, so username can be whatever
      client.username_pw_set(
          username='unused',
          password=create_jwt(cur_time, project_id, ssl_private_key_filepath, ssl_algorithm))

      client.on_connect = on_connect
      client.on_publish = on_publish

      client.tls_set(ca_certs=root_cert_filepath) # Replace this with 3rd party cert if that was used when creating registry
      client.connect(googleMQTTURL, googleMQTTPort)

      jwt_refresh = time.time() + ((token_life - 1) * 60) #set a refresh time for one minute before the JWT expires

      client.loop_start()

      last_checked = 0
      while time.time() < jwt_refresh: # as long as the JWT isn't ready to expire, otherwise break this loop so the JWT gets refreshed
        # Continuously monitor for heart beat signals being received
        try:
#	    inputReceived = io.input(receiver_in) # inputReceived will either be 1 or 0
            inputReceived = dhtDevice.temperature
            temperature_c = inputReceived
            currentTime = datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
            uniqueID = str(uuid.uuid4()) + "-" + sensorID
            payload = createJSON(sensorID, uniqueID, currentTime, temperature_c)
            client.publish(_MQTT_TOPIC, payload, qos=1)
            print("{}\n".format(payload))
            time.sleep(0.5)
            previousInput = inputReceived
        except Exception as e:
          print("There was an error")
          print(e)

      client.loop_stop()

if __name__ == '__main__':
	main()
