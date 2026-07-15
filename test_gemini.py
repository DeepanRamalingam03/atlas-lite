from clients.factory import ClientFactory

client = ClientFactory.create("gemini")

response = client.generate(
    "Reply with exactly: Gemini Worker Connected"
)

print(response)
