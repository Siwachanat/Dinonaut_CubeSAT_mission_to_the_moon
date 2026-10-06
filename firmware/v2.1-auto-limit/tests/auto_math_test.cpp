#include "ADCS_ControlMath.h"
static_assert(adcsPDCommand(0,10,2,1,2)==-10,"brake at target");
static_assert(adcsPDCommand(1,-10,2,1,2)==10,"damping inside deadband");
static_assert(adcsPDCommand(0,0,2,1,2)==0,"rest at target");
static_assert(adcsPDCommand(2,0,2,1,2)==4,"positive boundary");
static_assert(adcsPDCommand(-2,0,2,1,2)==-4,"negative boundary");
static_assert(adcsClampCommand(90,-30,30)==30,"positive saturation");
static_assert(adcsClampCommand(-90,-30,30)==-30,"negative saturation");
static_assert(adcsClampCommand(12,-30,30)==12,"preserve small correction");
static_assert(adcsClampCommand(40,0,30)==30,"momentum cap");
static_assert(adcsClampCommand(-10,0,30)==0,"momentum lower bound");
