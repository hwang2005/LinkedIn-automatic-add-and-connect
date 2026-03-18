# =============================================
# CONNECT-RELATED XPATHS
# =============================================

# XPATH for CONNECT button.
STATUS_CONNECT = "/html/body/div/div[3]/div/div/div[2]/div/div/main/section[1]/div[2]/div[3]/div/button[1]"

# XPATH for MESSAGE button (connect page).
STATUS_MESSAGE = "/html/body/div/div[3]/div/div/div[2]/div/div/main/section[1]/div[2]/div[3]/div/div[1]/button"

# XPATH for MORE button.
BUTTON_MORE = "/html/body/div/div[3]/div/div/div[2]/div/div/main/section[1]/div[2]/div[3]/div/div[2]/button"

# XPATH for CONNECT option when clicking MORE.
MORE_UNCONNECT = "/html/body/div/div[3]/div/div/div[2]/div/div/main/section[1]/div[2]/div[3]/div/div[2]/div/div/ul/li[3]/div"

# XPATH for UNCONNECT option when clicking MORE.
MORE_CONNECT = "/html/body/div/div[3]/div/div/div[2]/div/div/main/section[1]/div[2]/div[3]/div/div[2]/div/div/ul/li[3]/div"

# XPATH for ADD A NOTE button.
BUTTON_ADD_NOTE = "/html/body/div[3]/div/div/div[3]/button[1]"

# XPATH for NOTE textarea (multiple variants for different account types).
TEXTAREA_NOTE = [
    "/html/body/div[3]/div/div/div[3]/div[1]/textarea",         # NORMAL ACCOUNT.
    "/html/body/div[3]/div/div/div[2]/div[2]/div[1]/textarea"   # PREMIUM ACCOUNT.
]

# XPATH for SEND NOTE button (multiple variants for different account types).
BUTTON_SEND_NOTE = [
    "/html/body/div[3]/div/div/div[4]/button[2]",               # NORMAL ACCOUNT.
    "/html/body/div[3]/div/div/div[3]/button[3]"                # PREMIUM ACCOUNT.
]

# XPATH for SEND WITHOUT NOTE button.
BUTTON_SEND_WITHOUT_NOTE = "/html/body/div[4]/div/div/div[3]/button[2]"

# XPATH for VERIFY NOTE text field.
TEXTFIELD_VERIFY_NOTE = "/html/body/div[3]/div/div/div[2]/label/input"

# =============================================
# MESSAGE-RELATED XPATHS
# =============================================

# XPATH for MESSAGE button (message page).
BUTTON_MESSAGE = "/html/body/div[6]/div[3]/div/div/div[2]/div/div/main/section[1]/div[2]/div[3]/div/div[1]/button"

# CLASS NAME for message input field.
FIELD_MESSAGE = "msg-form__contenteditable"

# CLASS NAME for attachment upload input.
FIELD_ATTACHMENT = "msg-form__attachment-upload-input"

# CLASS NAME for send message button.
BUTTON_SUBMIT_MESSAGE = "msg-form__send-button"

# XPATH for close message dialog button.
BUTTON_CLOSE_MESSAGE = "/html/body/div[6]/div[4]/aside[1]/div[2]/div[1]/header/div[4]/button[3]"