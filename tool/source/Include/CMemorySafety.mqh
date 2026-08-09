//+------------------------------------------------------------------+
//| CMemorySafety — pointer validation helpers                       |
//+------------------------------------------------------------------+
#ifndef VCK_CMEMORYSAFETY_MQH
#define VCK_CMEMORYSAFETY_MQH

#define SAFE_DELETE(p)                         \
   do                                          \
     {                                         \
      if(CheckPointer(p) == POINTER_DYNAMIC)   \
        {                                      \
         delete p;                             \
         p = NULL;                             \
        }                                      \
     }                                         \
   while(false)

#define POINTER_IS_VALID(p) (CheckPointer(p) != POINTER_INVALID)

#endif // VCK_CMEMORYSAFETY_MQH
