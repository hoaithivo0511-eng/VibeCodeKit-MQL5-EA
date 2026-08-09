//+------------------------------------------------------------------+
//| CMagicRegistry.mqh                                                |
//|                                                                   |
//| File-backed reservation of EA magic numbers.                      |
//|                                                                   |
//| Storage: %APPDATA%/MetaQuotes/.../Files/magic_registry.json       |
//| Format (one entry per line, tab-separated, JSON-safe but flat):   |
//|   <magic>\t<owner>\t<reserved_at_unix_ts>                          |
//|                                                                   |
//| Public API:                                                       |
//|   bool Reserve(long magic, const string owner = NULL)              |
//|   bool Check  (long magic)                                         |
//|   int  List   (long &out[])                                        |
//+------------------------------------------------------------------+
#ifndef __CMAGIC_REGISTRY_MQH__
#define __CMAGIC_REGISTRY_MQH__

class CMagicRegistry
  {
private:
   string            m_filename;

   bool              ReadAll(long &magics[], string &owners[]);
   bool              Append(long magic, const string owner);

public:
                     CMagicRegistry(const string fname = "magic_registry.json");
                    ~CMagicRegistry(void) {}

   bool              Reserve(long magic, const string owner = NULL);
   bool              Check  (long magic);
   int               List   (long &out[]);
   string            FileName(void) const { return m_filename; }
  };

//+------------------------------------------------------------------+
CMagicRegistry::CMagicRegistry(const string fname = "magic_registry.json")
  : m_filename(fname)
  {
  }

//+------------------------------------------------------------------+
//| Read every line as `<magic>\t<owner>\t<ts>`. Tolerates legacy     |
//| single-column files (just `<magic>`).                              |
//+------------------------------------------------------------------+
bool CMagicRegistry::ReadAll(long &magics[], string &owners[])
  {
   ArrayResize(magics, 0);
   ArrayResize(owners, 0);
   int handle = FileOpen(m_filename, FILE_READ | FILE_TXT | FILE_ANSI | FILE_COMMON);
   if(handle == INVALID_HANDLE) return(true); // empty registry is OK
   while(!FileIsEnding(handle))
     {
      string line = FileReadString(handle);
      if(StringLen(line) == 0) continue;
      string parts[];
      int n = StringSplit(line, '\t', parts);
      if(n < 1) continue;
      long m = (long)StringToInteger(parts[0]);
      string own = (n >= 2) ? parts[1] : "";
      int sz = ArraySize(magics);
      ArrayResize(magics, sz + 1);
      ArrayResize(owners, sz + 1);
      magics[sz] = m;
      owners[sz] = own;
     }
   FileClose(handle);
   return(true);
  }

//+------------------------------------------------------------------+
bool CMagicRegistry::Append(long magic, const string owner)
  {
   int handle = FileOpen(m_filename,
                         FILE_WRITE | FILE_READ | FILE_TXT | FILE_ANSI | FILE_COMMON);
   if(handle == INVALID_HANDLE) return(false);
   FileSeek(handle, 0, SEEK_END);
   string line = IntegerToString(magic) + "\t" + owner + "\t"
                 + IntegerToString((long)TimeCurrent()) + "\n";
   FileWriteString(handle, line);
   FileClose(handle);
   return(true);
  }

//+------------------------------------------------------------------+
//| Returns true on first reservation; false if magic already taken.  |
//+------------------------------------------------------------------+
bool CMagicRegistry::Reserve(long magic, const string owner = NULL)
  {
   string who = (owner == NULL || owner == "") ? "unknown" : owner;
   // Atomic check-and-append: hold ONE exclusive handle across the scan and
   // the append so two EAs initialising concurrently cannot both reserve the
   // same magic (the old ReadAll-then-Append had a TOCTOU race). FileOpen
   // without FILE_SHARE_* is exclusive; retry briefly if another instance
   // currently holds the registry file.
   for(int tries = 0; tries < 50; ++tries)
     {
      int handle = FileOpen(m_filename,
                            FILE_READ | FILE_WRITE | FILE_TXT | FILE_ANSI | FILE_COMMON);
      if(handle == INVALID_HANDLE)
        {
         Sleep(20);
         continue;
        }
      bool taken = false;
      while(!FileIsEnding(handle))
        {
         string line = FileReadString(handle);
         if(StringLen(line) == 0) continue;
         string parts[];
         int n = StringSplit(line, '\t', parts);
         if(n < 1) continue;
         if((long)StringToInteger(parts[0]) == magic)
           {
            taken = true;
            break;
           }
        }
      if(taken)
        {
         FileClose(handle);
         return(false);
        }
      FileSeek(handle, 0, SEEK_END);
      string entry = IntegerToString(magic) + "\t" + who + "\t"
                     + IntegerToString((long)TimeCurrent()) + "\n";
      FileWriteString(handle, entry);
      FileClose(handle);
      return(true);
     }
   return(false); // registry stayed locked past the retry budget
  }

//+------------------------------------------------------------------+
//| Returns true if `magic` is already reserved by any EA.            |
//+------------------------------------------------------------------+
bool CMagicRegistry::Check(long magic)
  {
   long   magics[]; string owners[];
   ReadAll(magics, owners);
   for(int i = 0; i < ArraySize(magics); i++)
      if(magics[i] == magic) return(true);
   return(false);
  }

//+------------------------------------------------------------------+
//| Populate `out` with all reserved magics; returns count.           |
//+------------------------------------------------------------------+
int CMagicRegistry::List(long &out[])
  {
   string owners[];
   ReadAll(out, owners);
   return(ArraySize(out));
  }

#endif // __CMAGIC_REGISTRY_MQH__
