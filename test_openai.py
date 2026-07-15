from clients.factory import ClientFactory

client = ClientFactory.create("openai")

response = client.generate(
    "Reply with exactly: OpenAI Manager Connected"
)

print(response)
