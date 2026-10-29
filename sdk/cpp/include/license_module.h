#ifndef LICENSE_MODULE_H
#define LICENSE_MODULE_H
#include <stdint.h>
#ifdef _WIN32
#  ifdef LM_BUILDING_DLL              /* v1+ задаётся только при сборке самой библиотеки */
#    define LM_API __declspec(dllexport)
#  else
#    define LM_API __declspec(dllimport)
#  endif
#else
#  define LM_API __attribute__((visibility("default")))
#endif
#ifdef __cplusplus
extern "C" {
#endif

#define LM_ABI_VERSION 1

typedef enum {
    LM_OK = 0,
    LM_ERR_INVALID_KEY = -1,          /* key_not_found, invalid_key_format, product_mismatch */
    LM_ERR_DEVICE_LIMIT = -2,         /* seats_exhausted */
    LM_ERR_NETWORK = -3,              /* нет связи, 5xx, 503 maintenance */
    LM_ERR_INVALID_SIGNATURE = -4,    /* аренда или файл не прошли проверку */
    LM_ERR_EXPIRED = -5,              /* license_expired */
    LM_ERR_REVOKED = -6,              /* license_revoked; license_suspended (активация отклонена) */
    LM_ERR_CLOCK_ROLLBACK = -7,
    LM_ERR_REBIND_REQUIRED = -8,      /* v1+ 412; модуль повторяет активацию сам */
    LM_ERR_RELEASED = -9,             /* v1+ 410 */
    LM_ERR_RATE_LIMITED = -10,        /* v1+ 429 */
    LM_ERR_INSTANCE_CONFLICT = -11,   /* v1+ 409 instance_conflict */
    LM_ERR_INVALID_FILE = -12,        /* v1+ файл повреждён, чужой nonce, истёк срок ответа */
    LM_ERR_UNSUPPORTED = -13,         /* v1+ функция недоступна в этой версии */
    LM_ERR_NOT_INITIALIZED = -14,     /* v1+ */
    LM_ERR_BUFFER_TOO_SMALL = -15,    /* v1+ */
    LM_ERR_UPGRADE_REQUIRED = -16,    /* v1+ 426 */
    LM_ERR_STORE_CORRUPTED = -17,     /* v1+ только LM_Initialize[Ex]: хранилище повреждено и создано заново, модуль работает */
    LM_ERR_INTERNAL = -99
} LM_Result;

typedef enum {
    LM_MODE_TRIAL = 0,
    LM_MODE_FULL = 1,
    LM_MODE_SOFT_BLOCK = 2,           /* триал истёк, ключ не введён (UNLICENSED) */
    LM_MODE_LIMITED = 3,              /* мягкий блок (RESTRICTED) */
    LM_MODE_REVOKED = 4,
    LM_MODE_NOTICE = 5,               /* v1+ напоминание о сроке */
    LM_MODE_GRACE = 6,                /* v1+ отсрочка */
    LM_MODE_BLOCKED = 7               /* v1+ жёсткий блок */
} LM_LicenseMode;

typedef enum {
    LM_ACT_ONLINE = 0,
    LM_ACT_OFFLINE_FILE = 1,
    LM_ACT_OFFLINE_PHONE = 2          /* этап 2; до этого LM_ERR_UNSUPPORTED */
} LM_ActivationMode;

/* Структура из ТЗ — без изменений */
typedef struct {
    LM_LicenseMode mode;
    int trial_days_left;
    char license_type[32];
    int64_t expires_at;               /* Unix, 0 = бессрочно */
    char features[256];               /* JSON-массив функций */
} LM_LicenseStatus;

/* v1+ расширенный статус; поле struct_size заполняет вызывающий */
typedef struct {
    uint32_t struct_size;
    LM_LicenseMode mode;
    int32_t enforcement_monitor;      /* 1 = «прогрев», функции не ограничиваются */
    int32_t days_left;                /* до valid_until, отрицательное — после срока */
    int32_t trial_days_left;
    int64_t valid_until;              /* 0 = бессрочно */
    int64_t support_until;
    int64_t last_check_at;
    int64_t next_check_at;
    char license_type[32];
    char edition[64];
    char customer_name[256];
    char activation_id[40];
    char server_url[256];
    int32_t offline;                  /* 1 = активация файлами */
} LM_LicenseStatusEx;

/* v1+ */
typedef struct {
    uint32_t struct_size;
    const char* product_code;         /* "alteroffice-desktop" */
    const char* app_version;
    const char* server_url;           /* NULL = из config.json */
    const char* data_dir;             /* NULL = по умолчанию для ОС */
    const char* locale;               /* "ru" */
    uint32_t flags;                   /* LM_FLAG_NO_BACKGROUND_CHECK = 1 */
} LM_Config;

typedef struct {
    uint32_t struct_size;
    const char* id;
    const char* severity;             /* info | warning | critical */
    const char* placement;            /* banner | dialog | about | tray */
    const char* text;                 /* уже с подстановками, на языке locale */
    const char* action_label;
    const char* action_url;
} LM_Message;

typedef struct {
    uint32_t struct_size;
    int64_t documents_opened;         /* -1 = не передавать */
    const char* extra_json;           /* дополнительные счётчики по каталогу, NULL */
} LM_Usage;

typedef enum {
    LM_EVENT_STATE_CHANGED = 1,
    LM_EVENT_MESSAGE = 2,
    LM_EVENT_LEASE_UPDATED = 3,
    LM_EVENT_CHECK_FAILED = 4
} LM_EventType;

typedef void (*LM_EventCallback)(LM_EventType type, void* ctx);

/* --- функции из ТЗ --- */
LM_API int       LM_Initialize(const char* app_version);
LM_API LM_Result LM_GetStatus(LM_LicenseStatus* status);
LM_API LM_Result LM_Activate(const char* short_key, LM_ActivationMode mode);
LM_API LM_Result LM_ActivateFromFile(const char* response_file_path);
LM_API LM_Result LM_ActivateByPhone(const char* response_code);
LM_API LM_Result LM_Deactivate(void);
LM_API LM_Result LM_GenerateOfflineRequest(const char* short_key, const char* output_file_path);
LM_API LM_Result LM_GetHwid(char* buffer, int buffer_size);
LM_API void      LM_Shutdown(void);

/* --- v1+ --- */
LM_API LM_Result LM_InitializeEx(const LM_Config* config);
LM_API LM_Result LM_GetStatusEx(LM_LicenseStatusEx* status);
LM_API int       LM_HasFeature(const char* feature);            /* 1 / 0 */
LM_API LM_Result LM_CheckNow(void);                             /* синхронно, до 30 с */
LM_API LM_Result LM_SetCallback(LM_EventCallback cb, void* ctx);
LM_API int       LM_GetMessageCount(void);
LM_API LM_Result LM_GetMessage(int index, LM_Message* message); /* строки живут до следующего вызова */
LM_API LM_Result LM_MarkMessageShown(const char* message_id);
LM_API LM_Result LM_ReportUsage(const LM_Usage* usage);
LM_API LM_Result LM_GenerateRenewRequest(const char* output_file_path);
LM_API LM_Result LM_GenerateReleaseRequest(const char* output_file_path);
LM_API LM_Result LM_SetServerUrl(const char* url);
LM_API LM_Result LM_GetLastError(char* buffer, int buffer_size); /* user_message последней ошибки, UTF-8 */
LM_API int       LM_GetAbiVersion(void);
LM_API LM_Result LM_GetVersion(char* buffer, int buffer_size);  /* v1+ версия модуля SemVer, UTF-8; без инициализации */

#ifdef __cplusplus
}
#endif
#endif
