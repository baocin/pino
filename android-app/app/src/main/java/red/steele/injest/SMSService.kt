package red.steele.injest

import android.Manifest
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.provider.ContactsContract
import android.provider.Telephony
import android.telephony.SmsMessage
import android.util.Log
import androidx.core.content.ContextCompat
import org.json.JSONObject

class SMSService : BroadcastReceiver() {
    private lateinit var context: Context
    private lateinit var webSocketManager: WebSocketManager

    companion object {
        private const val TAG = "SMSService"
    }

    override fun onReceive(context: Context, intent: Intent) {
        try {
            this.context = context
            webSocketManager = WebSocketManager(AppState.serverIp)
            Log.d(TAG, "onReceive triggered with action: ${intent.action}")

            if (intent.action == Telephony.Sms.Intents.SMS_RECEIVED_ACTION || intent.action == "android.provider.Telephony.SMS_SENT") {
                Log.d(TAG, "SMS action detected: ${intent.action}")
                val bundle = intent.extras
                if (bundle == null) {
                    Log.d(TAG, "Bundle is null")
                    return
                }

                val pdus = bundle.get("pdus") as? Array<*>
                if (pdus == null) {
                    Log.d(TAG, "PDUs are null")
                    return
                }

                val messages = pdus.mapNotNull { pdu ->
                    try {
                        SmsMessage.createFromPdu(pdu as ByteArray)
                    } catch (e: Exception) {
                        Log.e(TAG, "Error creating SmsMessage from PDU", e)
                        null
                    }
                }
                if (messages.isEmpty()) {
                    Log.d(TAG, "No SMS messages found")
                    return
                }

                messages.forEach { message ->
                    val phoneNumber = message.originatingAddress
                    val contactName = getContactName(context, phoneNumber)

                    val smsData = JSONObject()
                    smsData.put("phoneNumber", phoneNumber)
                    smsData.put("contactName", contactName)
                    smsData.put("message", message.messageBody)
                    smsData.put("type", if (intent.action == Telephony.Sms.Intents.SMS_RECEIVED_ACTION) "received" else "sent")

                    Log.d(TAG, "SMS data prepared: $smsData")
                }
            } else {
                Log.d(TAG, "Received action is not SMS_RECEIVED_ACTION or SMS_SENT")
            }
        } catch (e: Exception) {
            Log.e(TAG, "Error processing SMS", e)
        }
    }

    private fun getContactName(context: Context, phoneNumber: String?): String {
        if (ContextCompat.checkSelfPermission(context, Manifest.permission.READ_CONTACTS) != PackageManager.PERMISSION_GRANTED) {
            Log.d(TAG, "Permission to read contacts not granted")
            return phoneNumber.toString()  // Default to phone number if permission is not granted
        }

        val uri = Uri.withAppendedPath(ContactsContract.PhoneLookup.CONTENT_FILTER_URI, Uri.encode(phoneNumber))
        val cursor = context.contentResolver.query(uri, null, null, null, null)
        var contactName = phoneNumber.toString()  // Default to phone number if contact name is not found

        if (cursor != null) {
            try {
                if (cursor.moveToFirst()) {
                    val contactIndex = cursor.getColumnIndex(ContactsContract.CommonDataKinds.Phone.DISPLAY_NAME)
                    contactName = cursor.getString(contactIndex) ?: phoneNumber.toString()
                }
            } catch (e: Exception) {
                Log.e(TAG, "Error retrieving contact name", e)
            } finally {
                cursor.close()
            }
        }

        Log.d(TAG, "Retrieved contact name: $contactName for phone number: $phoneNumber")
        return contactName
    }
}