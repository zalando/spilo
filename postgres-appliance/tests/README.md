# Run tests

After building the image, you can test your image by:

1. Setting up the environment variable `SPILO_TEST_IMAGE` to test the specific image. If unset, the default will be `spilo`.
    ```
    export SPILO_TEST_IMAGE=<your_spilo_image>
    ```
2. Run the test:
    ```
    bash test_spilo.sh
    ```
    To enable debugging for an entire script when it runs:
    ```
    bash -x test_spilo.sh
    ```

The test will create multiple containers. They will be cleaned up by the last line before running `main` in `test_spilo.sh`. To keep and debug the containers after running the test, this part can be commented.
```
trap cleanup QUIT TERM EXIT
```
