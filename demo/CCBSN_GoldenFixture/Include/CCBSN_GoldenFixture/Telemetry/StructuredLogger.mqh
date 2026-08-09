// digits-tested: 5,4,3,2
#pragma once
class CStructuredLogger
  {
private: string m_file;
public:
 void Configure(const string name){m_file=name+"-events.csv";}
 void Event(const string event,const string detail,const double value=0.0)
   {PrintFormat("VCK_EVENT|%s|%s|%.8f",event,detail,value);int h=FileOpen(m_file,FILE_COMMON|FILE_CSV|FILE_READ|FILE_WRITE|FILE_SHARE_READ,';');if(h!=INVALID_HANDLE){FileSeek(h,0,SEEK_END);FileWrite(h,TimeToString(TimeCurrent(),TIME_DATE|TIME_SECONDS),event,detail,DoubleToString(value,8));FileClose(h);}}
  };
