#include <Arduino.h>
#include <BasicEncoder.h>
#include <TimerOne.h>

BasicEncoder encoder(10, 11);

const int DIP1_PIN = 4;
const int DIP2_PIN = 5;
const int DIP3_PIN = 6;
const int BUTTON_PIN = 3;


const int PRINT_ALL_MS = 100;
const float INTERVAL_OPTIONS[] = {500, 1000, 1500, 2000, 3000, 5000, 7000, 10000};
const unsigned long UPDATE_INTERVAL = 100;   // 200 milliseconds update interval
const int STEPS_PER_REVOLUTION = 24; // 24 steps per revolution
const int MAX_MEANTIMEINTERVAL = INTERVAL_OPTIONS[7]; // milliseconds time interval for the mean
const int MAX_BUFFERSIZE = 10000 / UPDATE_INTERVAL;


// unsigned long MEAN_TIME_INTERVAL = MAX_MEANTIMEINTERVAL; 
int encoderBuffer[MAX_BUFFERSIZE];
int bufferIndex = 0;
int MEAN_TIME_INTERVAL = MAX_MEANTIMEINTERVAL;
int BUFFER_SIZE = MAX_BUFFERSIZE;

unsigned long lastUpdateTime = 0;
unsigned long lastPrintTime = 0;
bool initialized = false;


int last_button_state = 0;
int last_dip1_state = 0;
int last_dip2_state = 0;
int last_dip3_state = 0;
int button_state = 0;
int dip1_state = 0;
int dip2_state = 0;
int dip3_state = 0;

void timer_service() {
  encoder.service();
}



void buffer_from_dips() {
  Serial.print("New Dip State: ");
  Serial.print(1-dip1_state); Serial.print(", ");
  Serial.print(1-dip2_state); Serial.print(", ");
  Serial.print(1-dip3_state); Serial.print(" -> ");
  int index = (1 - dip1_state) * 1 + (1 - dip2_state) * 2 + (1 - dip3_state) * 4;
  Serial.print(index); Serial.print(" | So seconds mean: ");
  float new_mean_timeinterval = INTERVAL_OPTIONS[index];
  Serial.println(new_mean_timeinterval);
  if (new_mean_timeinterval != MEAN_TIME_INTERVAL) {
    MEAN_TIME_INTERVAL = new_mean_timeinterval;
    BUFFER_SIZE = MEAN_TIME_INTERVAL / UPDATE_INTERVAL;
    Serial.print("BUFFER_SIZE "); Serial.println(BUFFER_SIZE);
  }      
}

void readPins() {
  if (dip1_state == HIGH) {
    Serial.println("dip1_state off");
  } else {
    Serial.println("dip1_state on ");
  }    
  if (dip2_state == HIGH) {
    Serial.println("dip2_state off");
  } else {
    Serial.println("dip2_state on ");
  }   
  if (dip3_state == HIGH) {
    Serial.println("dip3_state off");
  } else {
    Serial.println("dip3_state on ");
  }   
  Serial.flush();
  buffer_from_dips();
}

void setup() {
  Serial.begin(115200);
  while (!Serial) { delay(50); }
  Serial.println("Starting..");
  Timer1.initialize(UPDATE_INTERVAL); // Set timer to trigger every 200 milliseconds
  Timer1.attachInterrupt(timer_service);


  pinMode(DIP1_PIN, INPUT_PULLUP); 
  pinMode(DIP2_PIN, INPUT_PULLUP); 
  pinMode(DIP3_PIN, INPUT_PULLUP); 
  pinMode(BUTTON_PIN, INPUT_PULLUP);


  dip1_state = digitalRead(DIP1_PIN);
  last_dip1_state = dip1_state;
  dip2_state = digitalRead(DIP2_PIN); 
  last_dip2_state = dip2_state;
  dip3_state = digitalRead(DIP3_PIN);
  last_dip3_state = dip3_state;
  button_state = digitalRead(BUTTON_PIN);
  last_button_state = button_state;
  
  readPins();

  // Initialize encoder buffer with zeros
  for (int i = 0; i < BUFFER_SIZE; ++i) {
    encoderBuffer[i] = 0;
  }

  Serial.println("Started");
}



void service_buttons() {  
  button_state = digitalRead(BUTTON_PIN);
  dip1_state = digitalRead(DIP1_PIN);
  dip2_state = digitalRead(DIP2_PIN);
  dip3_state = digitalRead(DIP3_PIN);
  
  if (!initialized) {
    last_button_state = button_state;
    initialized = true;
  }
  if (button_state != last_button_state) {
    if (button_state == LOW) {
      Serial.write("button1_pressed\n");
    } else {
      Serial.write("button1_released\n");
    }    
    Serial.flush();
    buffer_from_dips();
    last_button_state = button_state;
  }

  if (dip1_state != last_dip1_state) {
    if (dip1_state == HIGH) {
      Serial.println("dip1_state off");
    } else {
      Serial.println("dip1_state on ");
    }    
    Serial.flush();
    buffer_from_dips();
    last_dip1_state = dip1_state;
    delay(20);
  }  

  if (dip2_state != last_dip2_state) {
    if (dip2_state == HIGH) {
      Serial.println("dip2_state off");
    } else {
      Serial.println("dip2_state on ");
    }    
    Serial.flush();
    buffer_from_dips();
    last_dip2_state = dip2_state;
    delay(20);
  }  
  if (dip3_state != last_dip3_state) {
    if (dip3_state == HIGH) {
      Serial.println("dip3_state off");
    } else {
      Serial.println("dip3_state on ");
    }    
    Serial.flush();
    buffer_from_dips();
    last_dip3_state = dip3_state;
    delay(20);
  }  

}



void loop() {
  unsigned long currentTime = millis();
  int encoderValue = encoder.get_count();

  if (currentTime - lastUpdateTime >= UPDATE_INTERVAL) {
    // Shift buffer and store the new encoder value
    bufferIndex = (bufferIndex + 1) % BUFFER_SIZE;
    encoderBuffer[bufferIndex] = encoderValue;

    // Calculate mean RPM based on buffer values
    float sumRpm = 0;
    int startIndex = (bufferIndex + 1) % BUFFER_SIZE; // Start index for calculating mean RPM

    
    for (int i = 0; i < BUFFER_SIZE - 1; ++i) {
      int encoderChange = encoderBuffer[startIndex] - encoderBuffer[(startIndex + 1) % BUFFER_SIZE];
      float rpm = (encoderChange * 60.0 * 1000) / (STEPS_PER_REVOLUTION * UPDATE_INTERVAL);
      sumRpm += rpm;
      startIndex = (startIndex + 1) % BUFFER_SIZE;
    }

    // Calculate the mean RPM
    float meanRpm = sumRpm / (BUFFER_SIZE - 1);

    if (currentTime - lastPrintTime >= PRINT_ALL_MS) {
      Serial.print("Average RPM (Last "); Serial.print(MEAN_TIME_INTERVAL); Serial.print(" ms): ");
      Serial.println(meanRpm, 2); // Print average RPM with 2 decimal places
      lastPrintTime = currentTime;
    }

    lastUpdateTime = currentTime;
  }

  service_buttons();
  delay(10); // Optional small delay
}
