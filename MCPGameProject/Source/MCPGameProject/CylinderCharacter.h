#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Character.h"
#include "CylinderCharacter.generated.h"

class USpringArmComponent;
class UCameraComponent;

UCLASS()
class MCPGAMEPROJECT_API ACylinderCharacter : public ACharacter
{
	GENERATED_BODY()

public:
	ACylinderCharacter();

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Camera")
	TObjectPtr<USpringArmComponent> CameraBoom;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Camera")
	TObjectPtr<UCameraComponent> FollowCamera;

protected:
	virtual void SetupPlayerInputComponent(UInputComponent* PlayerInputComponent) override;

	void MoveForward(float Value);
	void MoveRight(float Value);
	void Turn(float Value);
};
