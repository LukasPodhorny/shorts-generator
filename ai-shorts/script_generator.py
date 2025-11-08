from openai import OpenAI
from file_reader import extract_text
from avatar import Avatar
from avatars_config import AVATARS


class ScriptGenerator:
    def __init__(
        self,
        avatar: Avatar,
        model: str = "gpt-5",
        builtin_reader: bool = True,
        max_output_tokens: int = 1800,
    ):
        self.avatar = avatar
        self.model = model
        self.builtin_reader = builtin_reader
        self.max_output_tokens = max_output_tokens

        self.client = OpenAI()

    def _upload_files(self, files):
        uploaded_files = []

        for file in files:
            with open(file, "rb") as f:
                uploaded_file = self.client.files.create(file=f, purpose="user_data")

            uploaded_files.append(uploaded_file)

        return uploaded_files

    def _delete_files(self, files):
        for file in files:
            self.client.files.delete(file.id)

    def _prepare_builtin_input(self, content):
        return [
            {
                "role": "developer",
                "content": self.avatar.instructions,
            },
            {
                "role": "user",
                "content": content,
            },
        ]

    def _prepare_api_input(self, content, uploaded_files):
        return [
            {
                "role": "developer",
                "content": self.avatar.instructions,
            },
            {
                "role": "user",
                "content": [
                    *[
                        {
                            "type": "input_file",
                            "file_id": f.id,
                        }
                        for f in uploaded_files
                    ],
                    {
                        "type": "input_text",
                        "text": content,
                    },
                ],
            },
        ]

    def generate_script(
        self, files: list[str] | None = None, user_input: str | None = None
    ):
        if files == None and user_input == None:
            raise ValueError("Either 'files' or 'user_input' must be provided.")

        content = ""
        if user_input:
            content += "User input:\n\n" + user_input

        if files and len(files) > 0:
            if self.builtin_reader:
                for i in range(0, len(files)):
                    content += f"\n\nFile {i+1}:\n\n" + extract_text(files[i])

                input_data = self._prepare_builtin_input(content)
            else:
                uploaded_files = self._upload_files(files)
                input_data = self._prepare_api_input(content, uploaded_files)
        else:
            input_data = self._prepare_builtin_input(content)

        try:
            response = self.client.responses.create(
                model=self.model,
                input=input_data,
                max_output_tokens=self.max_output_tokens,
            )
        finally:
            if not self.builtin_reader:
                self._delete_files(uploaded_files)

        return response.output_text


if __name__ == "__main__":
    script_generator = ScriptGenerator(AVATARS["biden"], builtin_reader=False)
    script = script_generator.generate_script(["test_files/Photosynthesis.pdf"])
    print(script.output_text)
