#include <Braccio.h>
#include <Servo.h>

Servo base;
Servo shoulder;
Servo elbow;
Servo wrist_ver;
Servo wrist_rot;
Servo gripper;

struct Position {
  const char *name;
  int b;
  int s;
  int e;
  int wv;
  int wr;
  int g;
};

Position board[] = {
 {"A1",58,78,170,168,60,60},
  {"B1",63,76,168,174,60,60},
  {"C1",74,77,167,177,77,60},
  {"D1",83,77,167,180,85,60},
  {"E1",93,77,167,181,93,60},
  {"F1",104,77,167,180,104,60},
  {"G1",114,84,174,170,112,60},
  {"H1",122,77,167,173,118,60},

  {"A2",60,68,160,167,63,60},
  {"B2",67,69,160,171,71,60},
  {"C2",77,71,162,172,78,60},
  {"D2",85,72,163,174,86,60},
  {"E2",93,75,168,170,94,60},
  {"F2",102,76,168,169,102,60},
  {"G2",111,72,164,170,110,60},
  {"H2",119,69,161,171,118,60},

  {"A3",64,59,152,163,66,60},
  {"B3",71,63,157,165,73,60},
  {"C3",78,65,157,167,80,60},
  {"D3",86,59,151,161,87,60},
  {"E3",93,67,160,166,94,60},
  {"F3",101,68,160,167,102,60},
  {"G3",109,64,156,168,110,60},
  {"H3",116,62,154,165,120,60},

  {"A4",67,54,147,159,69,60},
  {"B4",73,57,151,160,73,60},
  {"C4",80,59,153,160,80,60},
  {"D4",87,49,143,160,89,60},
  {"E4",94,59,153,162,94,60},
  {"F4",101,59,153,163,101,60},
  {"G4",108,58,151,162,108,60},
  {"H4",114,55,150,161,115,60},

  {"A5",70,42,141,153,69,60},
  {"B5",77,41,137,159,80,60},
  {"C5",81,44,142,159,80,60},
  {"D5",88,50,142,160,80,60},
  {"E5",94,52,143,160,80,60},
  {"F5",100,52,143,160,97,60},
  {"G5",107,50,143,160,107,60},
  {"H5",113,41,135,160,110,60},

  {"A6",73,35,137,147,72,60},
  {"B6",78,37,137,148,77,60},
  {"C6",82,39,137,152,75,60},
  {"D6",89,39,137,153,77,60},
  {"E6",94,39,137,154,83,60},
  {"F6",100,38,137,152,93,60},
  {"G6",106,38,136,152,97,60},
  {"H6",112,36,135,150,110,60},

  {"A7",74,26,124,141,79,60},
  {"B7",79,28,126,144,79,60},
  {"C7",84,29,126,146,79,60},
  {"D7",89,29,126,147,81,60},
  {"E7",96,33,128,143,81,60},
  {"F7",99,29,126,148,87,60},
  {"G7",105,27,126,151,104,60},
  {"H7",110,26,124,146,105,60},

  {"A8",77,13,111,133,82,60},
  {"B8",80,19,117,139,81,60},
  {"C8",84,20,117,139,81,60},
  {"D8",90,21,117,139,81,60},
  {"E8",94,21,117,139,85,60},
  {"F8",99,20,117,140,87,60},
  {"G8",104,18,117,140,92,60},
  {"H8",109,13,110,138,82,60},
  {"H9",120,13,110,138,82,60}
};

const int BOARD_SIZE = sizeof(board) / sizeof(board[0]);

const int GRIPPER_OPEN = 60;
const int GRIPPER_CLOSED = 73;

Position* findPosition(String name) {
  name.trim();
  name.toUpperCase();

  for (int i = 0; i < BOARD_SIZE; i++) {
    if (name.equals(board[i].name)) {
      return &board[i];
    }
  }

  return NULL;
}

void moveWrist(Position *position, int gripperPosition, int wristPosition){
   Braccio.ServoMovement(
    20,
    position->b,
    position->s,
    position->e,
    wristPosition,
    position->wr,
    gripperPosition
  );
}

void moveArm(Position *position, int gripperPosition) {
  Braccio.ServoMovement(
    20,
    position->b,
    position->s,
    position->e,
    position->wv,
    position->wr,
    gripperPosition
  );
}

void moveToCalibrationPosition() {
  Serial.println("Volviendo a calibracion...");

  Braccio.ServoMovement(
    20,
    0,
    48,
    180,
    0,
    180,
    73
  );

  delay(100);

  Serial.println("Brazo calibrado y esperando.");
  Serial.println("Escribi una orden, por ejemplo: A1 H5");
  Serial.println();
}

void safePosition(int gripperPosition) {
  Braccio.ServoMovement(
    20,
    90,
    80,
    140,
    120,
    90,
    gripperPosition
  );
}

void movePiece(Position *start, Position *destination) {
  // Ir al origen con la garra abierta en 60
  moveToCalibrationPosition();
  delay(500);
  moveArm(start, GRIPPER_OPEN);
  delay(500);

  // Cerrar la garra y agarrar la pieza
  moveArm(start, GRIPPER_CLOSED);
  delay(500);

  // Levantar la pieza a la posición segura (sin pasar por calibración)
  safePosition(GRIPPER_CLOSED);
  delay(700);
    moveToCalibrationPosition();
  delay(500);

  // Ir directamente desde la posición segura hasta el destino
  moveArm(destination, GRIPPER_CLOSED);
  delay(500);

  // Soltar la pieza abriendo solo hasta 60
  moveArm(destination, GRIPPER_OPEN);
  delay(500);

  // Volver a la posición segura con la garra en 60
   moveWrist(destination, 110, GRIPPER_OPEN);
   delay(500);
  safePosition(GRIPPER_OPEN);
  delay(700);
 

  Serial.println("Movimiento terminado");
}

void setup() {
  Serial.begin(9600);
  Serial.setTimeout(100);

  Braccio.begin();

  Serial.println("Escriba origen y destino");
  Serial.println("Ejemplo: A1 H5");
}

void loop() {
  if (Serial.available() == 0) {
    return;
  }

  String command = Serial.readStringUntil('\n');
  command.trim();
  command.toUpperCase();

  int separator = command.indexOf(' ');

  if (separator == -1) {
    Serial.println("Formato invalido. Ejemplo: A1 H5");
    return;
  }

  String startName = command.substring(0, separator);
  String destinationName = command.substring(separator + 1);

  startName.trim();
  destinationName.trim();

  Position *start = findPosition(startName);
  Position *destination = findPosition(destinationName);

  if (start == NULL || destination == NULL) {
    Serial.println("Casilla invalida");
    return;
  }

  Serial.print("Moviendo de ");
  Serial.print(startName);
  Serial.print(" hacia ");
  Serial.println(destinationName);



  movePiece(start, destination);
}
