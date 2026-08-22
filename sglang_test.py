import sglang as sgl

@sgl.function
def test_generation(s, question):
    s += sgl.user(question)
    s += sgl.assistant(sgl.gen("answer", max_tokens=128))

def main():
    # Set the backend to the local server running on port 30000
    sgl.set_default_backend(sgl.RuntimeEndpoint("http://localhost:30000"))
    
    print("Sending prompt to local SGLang server...")
    state = test_generation.run(question="Explain the theory of relativity in 2 sentences.")
    
    print("\n--- Response ---")
    print(state["answer"])

if __name__ == "__main__":
    main()
