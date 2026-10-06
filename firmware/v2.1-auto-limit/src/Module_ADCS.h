#pragma once

/* SunSeek Platform v2.0 — MODULE LAYER */
#include <Arduino.h>
#include <math.h>
#include "Config_ADCS.h"
#include "ADCS_ControlMath.h"
#include "Module_IMU.h"
#include "Module_SunSensor.h"
#include "Module_ReactionWheel.h"
#include "Module_Estimator.h"

enum ADCSMode { ADCS_MANUAL, ADCS_AUTO };
enum ADCSReference { ADCS_SUN, ADCS_MAG };

struct ADCSState {
  ADCSMode mode;
  ADCSReference ref;
  float target, kp, kd;
  int bias;

  // Raw sensor-domain errors retained for Engineering telemetry.
  float sunError, magError;

  // Controller-domain values.
  float error, rate, u;

  // Estimation chain.
  float rawReference;
  float filteredReference;
  float estimatedAngle;

  bool valid;
};

static ADCSState _a = {
  ADCS_MANUAL, ADCS_SUN,
  ADCS_DEFAULT_TARGET_DEG, ADCS_DEFAULT_KP, ADCS_DEFAULT_KD,
  RW_DEFAULT_BIAS_PERCENT,
  0, 0, 0, 0, 0,
  0, 0, 0,
  false
};

static unsigned long _aLast = 0;
static int _aCommandLimit = ADCS_DEFAULT_RW_LIMIT;
inline int adcsCommandLimit() { return _aCommandLimit; }
inline bool adcsSetCommandLimit(int limit) {
  if (_a.mode != ADCS_MANUAL || limit < 1 || limit > ADCS_MAX_RW_COMMAND) return false;
  _aCommandLimit = limit;
  return true;
}

inline float adcsWrap180(float x){ while(x>180)x-=360; while(x<=-180)x+=360; return x; }
inline const char* adcsModeText(){return _a.mode==ADCS_AUTO?"AUTO":"MANUAL";}
inline const char* adcsRefText(){return _a.ref==ADCS_MAG?"MAG":"SUN";}

inline void adcsBegin(){
  estimatorBegin();
  _aLast=millis();
}

inline ADCSState adcsGet(){return _a;}
inline void adcsManual(){_a.mode=ADCS_MANUAL;_a.u=0;}

inline bool adcsReference(ADCSReference r){
  if(_a.mode==ADCS_AUTO)return false;
  _a.ref=r;
  estimatorSetReference(r==ADCS_MAG ? EST_REF_MAG : EST_REF_SUN);
  return true;
}

inline bool adcsTarget(float t){
  if(_a.mode==ADCS_AUTO)return false;
  if(_a.ref==ADCS_SUN&&(t < -90 || t > 90))return false;
  if(_a.ref==ADCS_MAG&&(t<0||t>=360))return false;
  _a.target=t;
  return true;
}

inline bool adcsTune(float kp,float kd,int bias){
  if(kp<0||kp>ADCS_KP_MAX||kd<0||kd>ADCS_KD_MAX||bias<0||bias>100)return false;
  _a.kp=kp;_a.kd=kd;_a.bias=bias;return true;
}

inline bool adcsRead(){
  IMURawSample r;
  IMUProcessedSample p;
  SunSample s;
  if(!imuReadRaw(r)||!imuProcess(r,p)||!sunSensorRead(s)){
    _a.valid=false;
    return false;
  }

  _a.sunError = _a.target - s.angleDeg;
  _a.magError = adcsWrap180(_a.target - p.heading);
  _a.rate = p.bodyRate;

  _a.rawReference = (_a.ref==ADCS_MAG) ? p.heading : s.angleDeg;
  EstimatorReference er = (_a.ref==ADCS_MAG) ? EST_REF_MAG : EST_REF_SUN;
  if(!estimatorUpdate(_a.rawReference, _a.rate, er)){
    _a.valid=false;
    return false;
  }

  EstimatorState es = estimatorGet();
  _a.filteredReference = es.filteredReferenceDeg;
  _a.estimatedAngle = es.estimatedAngleDeg;

  // Controller now consumes the estimator output.
  // With LPF=OFF and Fusion=OFF this is equivalent to the verified v0.2 path.
  _a.error = (_a.ref==ADCS_MAG)
    ? adcsWrap180(_a.target - _a.estimatedAngle)
    : (_a.target - _a.estimatedAngle);

  _a.valid=true;
  return true;
}

inline bool adcsAuto(){
  if(!adcsRead())return false;
  rwStop();
  if(rwGetMode()==RW_MODE_MOMENTUM)rwSetBias(min(_a.bias,_aCommandLimit));
  _a.mode=ADCS_AUTO;
  _aLast=0;
  return true;
}

inline void adcsFault(){rwStop();_a.mode=ADCS_MANUAL;_a.u=0;_a.valid=false;}

inline void adcsUpdate(){
  // Sensor acquisition + estimator are spacecraft services, not AUTO-only.
  // Keep them alive in MANUAL so Engineering can characterize
  // Raw -> Filtered -> Estimated response without enabling the controller.
  unsigned long n=millis();
  if(n-_aLast<ADCS_CONTROL_PERIOD_MS)return;
  _aLast=n;

  if(!adcsRead()){
    if(_a.mode==ADCS_AUTO) adcsFault();
    else _a.valid=false;
    return;
  }

  // In MANUAL we update sensing/estimation only; actuator remains operator-controlled.
  if(_a.mode!=ADCS_AUTO)return;

  // Deadband suppresses pointing correction only, never gyro damping.
  float u=adcsPDCommand(_a.error,_a.rate,_a.kp,_a.kd,ADCS_DEADBAND_DEG);
  if(!isfinite(u)){adcsFault();return;}

  _a.u=u;

  // Bound AUTO PWM in both strategies; this is not a body-rate limit.
  if(rwGetMode()==RW_MODE_REACTION){
    int c=(int)roundf(adcsClampCommand(
      ADCS_CONTROL_SIGN*u,
      -(float)_aCommandLimit,
      (float)_aCommandLimit));
    rwSetReactionCommand(c);
  }else{
    int c=(int)roundf(adcsClampCommand(
      (float)_a.bias+ADCS_CONTROL_SIGN*u,
      0.0f,
      (float)_aCommandLimit));
    rwSetBias(c);
  }
}
